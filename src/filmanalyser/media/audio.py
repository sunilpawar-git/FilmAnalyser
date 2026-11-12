"""Audio decoding (DECISIONS #60). ffprobe says how many channels a film's first audio track has;
ffmpeg then decodes each chunk's window on its own, as 32-bit float PCM at AUDIO_RATE. One process
per window keeps no state between chunks, so a resumed run gets the same audio as an uninterrupted
one, and memory is bounded by the chunk.

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
from pathlib import Path
from typing import Any

import numpy as np

from filmanalyser.core.chunk import Audio, Chunk, Samples
from filmanalyser.core.config import (
    AUDIO_MAX_CHANNELS,
    AUDIO_RATE,
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
    """The first audio stream's channel count, as JSON. The path follows `--`."""
    return [
        ffprobe, "-v", "error", "-select_streams", "a:0",
        "-show_entries", "stream=channels", "-of", "json", "--", str(path),
    ]  # fmt: skip


def parse_audio_channels(text: str, name: str = "") -> int | None:
    """None when the film has no audio stream; else its channel count, at most AUDIO_MAX_CHANNELS
    (a multichannel track is downmixed by ffmpeg)."""
    try:
        data: Any = json.loads(text)
        streams = data["streams"]
    except (ValueError, KeyError, TypeError):
        raise DecodeError(key="error.decode.probe_failed", name=name) from None
    if not isinstance(streams, list):
        raise DecodeError(key="error.decode.probe_failed", name=name)
    if not streams:
        return None
    channels = streams[0].get("channels") if isinstance(streams[0], dict) else None
    if not isinstance(channels, int) or isinstance(channels, bool) or channels < 1:
        raise DecodeError(key="error.decode.probe_failed", name=name)
    return min(channels, AUDIO_MAX_CHANNELS)


def audio_channels(path: Path) -> int | None:
    """Channels of the film's first audio track (1 or 2), or None when it has no audio."""
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
    return parse_audio_channels(done.stdout.decode("utf-8", errors="replace"), path.name)


def decode_argv(
    ffmpeg: str, path: Path, start_s: float, duration_s: float, channels: int
) -> list[str]:
    """The one command line that decodes a window of audio to raw float32 on stdout."""
    if not (math.isfinite(start_s) and start_s >= 0 and math.isfinite(duration_s)):
        raise _bad_window()
    if duration_s <= 0 or not 1 <= channels <= AUDIO_MAX_CHANNELS:
        raise _bad_window()
    return [
        ffmpeg, "-nostdin", "-v", "error",
        "-ss", f"{start_s:.6f}", "-protocol_whitelist", "file", "-i", f"file:{path}",
        "-t", f"{duration_s:.6f}", "-map", "0:a:0", "-vn", "-sn", "-dn",
        "-ac", str(channels), "-ar", str(AUDIO_RATE),
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


def decode_window(path: Path, start_s: float, duration_s: float, channels: int) -> Samples:
    """`duration_s` of the film's audio from `start_s` (film time), as float32 (count, channels)."""
    argv = decode_argv(find_tool("ffmpeg"), path, start_s, duration_s, channels)
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
    count = max(1, round(duration_s * AUDIO_RATE))
    return _fit(done.stdout, count, channels)


def attach_audio(chunks: Iterable[Chunk], path: Path, channels: int) -> Iterator[Chunk]:
    """Each chunk with its audio window: the same span as its frames, overlap included."""
    for chunk in chunks:
        start = chunk.first_frame_s
        samples = decode_window(path, start, chunk.end_s - start, channels)
        yield dataclasses.replace(chunk, audio=Audio(AUDIO_RATE, start, samples))
