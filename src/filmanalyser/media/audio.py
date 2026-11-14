"""Audio decoding (DECISIONS #60, #72). ffprobe says how many channels a film's first audio track
has. ffmpeg then decodes each chunk's window on its own, as 32-bit float PCM: at AUDIO_RATE for
speech and at AUDIO_HIRES_RATE for loudness and true peak. One process per window keeps no state
between chunks, so a resumed run gets the same audio as an uninterrupted one, and memory is bounded
by the chunk.

Timing: the window starts at the chunk's first frame (film time, from the input seek). A track that
ends before the picture reads as silence after its end, so every window has exactly the length the
frames imply and the samples line up with the frames.

Security: argument-list subprocess only (`*_argv` builders), file: protocol only, numbers formatted
as fixed-point, a time limit on every run, and stderr scrubbed of paths before it is reported.
"""

import dataclasses
import json
import math
import subprocess
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from filmanalyser.core.chunk import Audio, Chunk, Samples
from filmanalyser.core.config import (
    AUDIO_MAX_CHANNELS,
    AUDIO_TIMEOUT_S,
    PROBE_MAX_OUTPUT_BYTES,
    PROBE_TIMEOUT_S,
    STDERR_LIMIT_BYTES,
)
from filmanalyser.core.errors import DecodeError, InputError
from filmanalyser.media.paths import find_tool, scrub_stderr

_FLOAT32_BYTES = 4


def _bad_window() -> InputError:
    return InputError(key="error.input.bad_setting", name="audio_window")


def audio_probe_argv(ffprobe: str, path: Path) -> list[str]:
    """The first audio stream's channel count and start time, as JSON. The path follows `--`."""
    return [
        ffprobe, "-v", "error", "-select_streams", "a:0",
        "-show_entries", "stream=channels,start_time", "-of", "json", "--", str(path),
    ]  # fmt: skip


@dataclass(frozen=True)
class AudioStream:
    """The film's first audio track: its channel count (at most AUDIO_MAX_CHANNELS) and the
    time its first sample sits on the container's clock (its start offset, often 0)."""

    channels: int
    start_s: float


def _start_time(stream: dict[str, Any], name: str) -> float:
    raw = stream.get("start_time", 0.0)
    try:
        value = float(raw)
    except (TypeError, ValueError):
        raise DecodeError(key="error.decode.probe_failed", name=name) from None
    if not math.isfinite(value):
        raise DecodeError(key="error.decode.probe_failed", name=name)
    return value


def parse_audio_stream(text: str, name: str = "") -> AudioStream | None:
    """None when the film has no audio stream; else its channels and start offset."""
    try:
        data: Any = json.loads(text)
        streams = data["streams"]
    except (ValueError, KeyError, TypeError):
        raise DecodeError(key="error.decode.probe_failed", name=name) from None
    if not isinstance(streams, list):
        raise DecodeError(key="error.decode.probe_failed", name=name)
    if not streams:
        return None
    stream = streams[0] if isinstance(streams[0], dict) else {}
    channels = stream.get("channels")
    if not isinstance(channels, int) or isinstance(channels, bool) or channels < 1:
        raise DecodeError(key="error.decode.probe_failed", name=name)
    return AudioStream(min(channels, AUDIO_MAX_CHANNELS), _start_time(stream, name))


def parse_audio_channels(text: str, name: str = "") -> int | None:
    stream = parse_audio_stream(text, name)
    return None if stream is None else stream.channels


def audio_stream(path: Path) -> AudioStream | None:
    """The film's first audio track (channels, start offset), or None when it has no audio."""
    argv = audio_probe_argv(find_tool("ffprobe"), path)
    try:
        done = subprocess.run(
            argv,
            check=False,
            capture_output=True,
            timeout=PROBE_TIMEOUT_S,
            stdin=subprocess.DEVNULL,
        )
    except subprocess.TimeoutExpired:
        raise DecodeError(key="error.decode.probe_failed", name=path.name) from None
    if done.returncode != 0 or len(done.stdout) > PROBE_MAX_OUTPUT_BYTES:
        detail = scrub_stderr(done.stderr, path, STDERR_LIMIT_BYTES)
        raise DecodeError(detail, key="error.decode.probe_failed", name=path.name)
    return parse_audio_stream(done.stdout.decode("utf-8", errors="replace"), path.name)


def audio_channels(path: Path) -> int | None:
    """Channels of the film's first audio track (1 or 2), or None when it has no audio."""
    stream = audio_stream(path)
    return None if stream is None else stream.channels


@dataclass(frozen=True)
class PcmFormat:
    """What a window is decoded to: its channel count and sample rate (float32 PCM)."""

    channels: int
    rate: int


@dataclass(frozen=True)
class Clock:
    """Where the picture and the audio track start on the container clock (DECISIONS #67)."""

    picture_start_s: float
    audio_start_s: float


def decode_argv(
    ffmpeg: str, path: Path, start_s: float, duration_s: float, pcm: PcmFormat
) -> list[str]:
    """The one command line that decodes a window of audio to raw float32 on stdout."""
    if not (math.isfinite(start_s) and start_s >= 0 and math.isfinite(duration_s)):
        raise _bad_window()
    if duration_s <= 0 or not 1 <= pcm.channels <= AUDIO_MAX_CHANNELS or pcm.rate <= 0:
        raise _bad_window()
    return [
        ffmpeg, "-nostdin", "-v", "error",
        "-ss", f"{start_s:.6f}", "-protocol_whitelist", "file", "-i", f"file:{path}",
        "-t", f"{duration_s:.6f}", "-map", "0:a:0", "-vn", "-sn", "-dn",
        "-ac", str(pcm.channels), "-ar", str(pcm.rate),
        "-f", "f32le", "-acodec", "pcm_f32le", "pipe:1",
    ]  # fmt: skip


def _fit(raw: bytes, count: int, channels: int) -> Samples:
    """The decoded bytes as (count, channels) float32: a short track is padded with silence (see the
    module docstring); anything past `count` is dropped."""
    frame = _FLOAT32_BYTES * channels
    usable = np.frombuffer(raw[: len(raw) - len(raw) % frame], dtype=np.float32)
    samples = np.zeros((count, channels), dtype=np.float32)
    got = min(count, len(usable) // channels)
    samples[:got] = usable[: got * channels].reshape(got, channels)
    return samples


def decode_window(path: Path, start_s: float, duration_s: float, pcm: PcmFormat) -> Samples:
    """`duration_s` of the film's audio from `start_s` (film time), as float32 (count, channels)."""
    argv = decode_argv(find_tool("ffmpeg"), path, start_s, duration_s, pcm)
    try:
        done = subprocess.run(
            argv,
            check=False,
            capture_output=True,
            timeout=AUDIO_TIMEOUT_S,
            stdin=subprocess.DEVNULL,
        )
    except subprocess.TimeoutExpired:
        raise DecodeError(key="error.decode.audio_failed", name=path.name) from None
    if done.returncode != 0:
        detail = scrub_stderr(done.stderr, path, STDERR_LIMIT_BYTES)
        raise DecodeError(detail, key="error.decode.audio_failed", name=path.name)
    count = max(1, round(duration_s * pcm.rate))
    return _fit(done.stdout, count, pcm.channels)


def audio_window(
    path: Path, container_start_s: float, audio_start_s: float, duration_s: float, pcm: PcmFormat
) -> Samples:
    """`duration_s` of audio starting at `container_start_s` on the container clock. A track that
    begins after that point (`audio_start_s`) leaves a lead of silence: ffmpeg's seek works on the
    container clock, so nothing before the track's first sample exists to decode."""
    count = max(1, round(duration_s * pcm.rate))
    lead = min(count, round(max(0.0, audio_start_s - container_start_s) * pcm.rate))
    out = np.zeros((count, pcm.channels), dtype=np.float32)
    if count > lead:
        decode_from = container_start_s + lead / pcm.rate
        out[lead:] = decode_window(path, decode_from, (count - lead) / pcm.rate, pcm)
    return out


def _attach(
    chunks: Iterable[Chunk], path: Path, pcm: PcmFormat, clock: Clock, hires: bool
) -> Iterator[Chunk]:
    """Each chunk with an audio window in `field`: the same span as its frames, overlap included."""
    for chunk in chunks:
        film_start = chunk.first_frame_s
        samples = audio_window(
            path, clock.picture_start_s + film_start, clock.audio_start_s,
            chunk.end_s - film_start, pcm,
        )  # fmt: skip
        window = Audio(pcm.rate, film_start, samples)
        if hires:
            yield dataclasses.replace(chunk, audio_hires=window)
        else:
            yield dataclasses.replace(chunk, audio=window)


def attach_audio(
    chunks: Iterable[Chunk], path: Path, pcm: PcmFormat, clock: Clock
) -> Iterator[Chunk]:
    """Chunks with their speech-rate audio (`audio`, AUDIO_RATE)."""
    return _attach(chunks, path, pcm, clock, hires=False)


def attach_hires(
    chunks: Iterable[Chunk], path: Path, pcm: PcmFormat, clock: Clock
) -> Iterator[Chunk]:
    """Chunks with their loudness-rate audio (`audio_hires`, AUDIO_HIRES_RATE)."""
    return _attach(chunks, path, pcm, clock, hires=True)
