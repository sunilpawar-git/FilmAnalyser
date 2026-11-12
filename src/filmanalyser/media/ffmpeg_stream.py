"""Streaming decode: ffmpeg writes downscaled raw RGB frames to a pipe, we read them one frame
at a time and hand them to the chunker. Memory depends on the chunk size, not the film length.

Security: argument-list `subprocess` (never a shell); the input is an absolute, validated path
forced through the `file:` protocol with every other protocol whitelisted away (so a crafted
playlist cannot make ffmpeg open network URLs); stdin is closed; stderr is drained by a thread
that keeps only the last STDERR_LIMIT_BYTES bytes, so a chatty or hostile stream cannot grow memory
or deadlock the pipe; the process is killed if the consumer stops early.
"""

import contextlib
import os
import subprocess
import threading
import time
from collections.abc import Generator, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import IO, cast

import numpy as np

from filmanalyser.core.chunk import Chunk, Frames, span_for
from filmanalyser.core.config import STDERR_LIMIT_BYTES, Config
from filmanalyser.core.errors import DecodeError
from filmanalyser.core.events import log_event
from filmanalyser.media.chunker import chunk_frames
from filmanalyser.media.paths import find_tool, scrub_stderr, validate_input_path
from filmanalyser.media.probe import probe_video
from filmanalyser.media.telemetry import peak_rss_mb

_DRAIN_READ = 4096
_JOIN_SECONDS = 5.0


@dataclass(frozen=True)
class Seek:
    """Where a decode starts (`start_s`, skipping the film before it) and the stream's own start
    time (`origin_s`, from the probe). Both keep the grid anchored to film time (DECISIONS #54)."""

    start_s: float = 0.0
    origin_s: float = 0.0


NO_SEEK = Seek()


def decode_argv(
    ffmpeg: str, path: Path, config: Config, size: tuple[int, int], seek: Seek = NO_SEEK
) -> list[str]:
    """The one place the ffmpeg command line is built. `-i` takes the next argument as its value
    (ffmpeg has no `--` for inputs: after it every argument is an output name), so the path is
    made safe instead: absolute, `file:`-prefixed, protocols whitelisted.

    Timing (DECISIONS #54): the 12 fps grid must be anchored to the film's own clock. The stream's
    start (`origin_s`, from the probe) is subtracted from the source timestamps. The first frame a
    seek decodes lies between source frames, so re-anchoring to it (`PTS-STARTPTS`) moved the grid
    and a resumed run sampled different frames. `-copyts` keeps those timestamps on the container's
    clock, so the grid does not depend on where a seek lands.
    """
    width, height = size
    skip = ["-ss", str(seek.start_s)] if seek.start_s > 0 else []
    video_filter = (
        f"setpts=PTS-{seek.origin_s}/TB,fps={config.analysis_fps},scale={width}:{height}:flags=area"
    )
    return [
        ffmpeg, "-nostdin", "-v", "error", "-copyts", *skip,
        "-protocol_whitelist", "file", "-i", f"file:{path}",
        "-map", "0:v:0", "-an", "-sn", "-dn",
        "-vf", video_filter,
        "-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1",
    ]  # fmt: skip


class _StderrTail:
    """Drains a pipe on a thread, remembering only its last `limit` bytes."""

    def __init__(self, stream: IO[bytes], limit: int) -> None:
        self._tail = b""
        self._limit = limit
        self._thread = threading.Thread(target=self._drain, args=(stream,), daemon=True)
        self._thread.start()

    def _drain(self, stream: IO[bytes]) -> None:
        # The pipe can be closed under us (process gone, or a straggler held it open): stop quietly.
        with contextlib.suppress(ValueError, OSError):
            for data in iter(lambda: stream.read(_DRAIN_READ), b""):
                self._tail = (self._tail + data)[-self._limit :]

    def finish(self) -> None:
        """Wait for the pipe to hit EOF. Must run before the Popen block closes the pipes."""
        self._thread.join(_JOIN_SECONDS)

    def text(self, path: Path) -> str:
        return scrub_stderr(self._tail, path, self._limit)


def stream_frames(
    path: Path, config: Config, size: tuple[int, int], seek: Seek = NO_SEEK
) -> Generator[Frames]:
    """Yield decoded frames, shape (height, width, 3), from `seek.start_s` until the film ends."""
    argv = decode_argv(find_tool("ffmpeg"), path, config, size, seek)
    width, height = size
    frame_bytes = width * height * 3
    with subprocess.Popen(
        argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE
    ) as proc:
        stdout, stderr = cast(IO[bytes], proc.stdout), cast(IO[bytes], proc.stderr)
        tail = _StderrTail(stderr, STDERR_LIMIT_BYTES)
        count = 0
        try:
            while len(raw := stdout.read(frame_bytes)) == frame_bytes:
                count += 1
                yield np.frombuffer(raw, dtype=np.uint8).reshape(height, width, 3)
            code = proc.wait()
        finally:
            if proc.poll() is None:
                proc.kill()  # the consumer stopped early, or something failed: never leak ffmpeg
            tail.finish()
    if code != 0:
        raise DecodeError(
            tail.text(path), key="error.decode.ffmpeg_failed", name=path.name, code=code
        )
    if count == 0:
        raise DecodeError(key="error.decode.no_frames", name=path.name)


def _timed(chunks: Iterator[Chunk], film: str) -> Iterator[Chunk]:
    """Pass chunks through, logging decode time and peak RSS for each (structured, no content)."""
    total = 0
    while True:
        began = time.perf_counter()
        chunk = next(chunks, None)
        if chunk is None:
            break
        total += 1
        log_event(
            "chunk",
            film=film,
            index=chunk.index,
            frames=len(chunk.frames),
            decode_s=round(time.perf_counter() - began, 4),
            peak_rss_mb=round(peak_rss_mb(), 1),
        )
        yield chunk
    log_event("decode_done", film=film, chunks=total)


def decode_chunks(
    raw_path: str | os.PathLike[str], config: Config, start_chunk: int = 0
) -> Iterator[Chunk]:
    """Validate, probe and stream a film as overlapping chunks (the Phase 2 entry point).

    `start_chunk` resumes a run: chunks before it are not decoded (only the overlap that chunk
    needs as context is), and the chunks that follow are identical to an uninterrupted run's."""
    path = validate_input_path(raw_path)
    info = probe_video(path)
    size = info.scaled_size(config.frame_width)
    span = span_for(start_chunk, config.frames_per_chunk, config.overlap_frames)
    log_event(
        "decode_start", film=path.name, width=size[0], height=size[1], fps=config.analysis_fps,
        start_chunk=start_chunk,
    )  # fmt: skip
    seek = Seek(span.context_start / config.analysis_fps, info.start_s)
    frames = stream_frames(path, config, size, seek)
    chunks = chunk_frames(frames, config, (size[1], size[0]), start_chunk)
    yield from _timed(chunks, path.name)
