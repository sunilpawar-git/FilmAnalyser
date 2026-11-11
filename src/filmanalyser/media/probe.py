"""ffprobe wrapper: the facts about a film the decoder needs (size, length, start offset)."""

import json
import math
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from filmanalyser.core.config import PROBE_MAX_OUTPUT_BYTES, PROBE_TIMEOUT_S, STDERR_LIMIT_BYTES
from filmanalyser.core.errors import DecodeError
from filmanalyser.media.paths import find_tool, scrub_stderr

_ENTRIES = "stream=width,height,duration,start_time:format=duration,start_time"


@dataclass(frozen=True)
class VideoInfo:
    width: int
    height: int
    duration_s: float
    start_s: float  # container timestamp of the first frame; the decoder normalises it to 0

    def scaled_size(self, width: int) -> tuple[int, int]:
        """(width, height) after scaling to `width`, keeping the aspect with an even height."""
        return width, max(2, round(width * self.height / self.width / 2) * 2)


def probe_argv(ffprobe: str, path: Path) -> list[str]:
    """Argument list (never a shell). The path comes last, after `--`, so it cannot be an option."""
    return [
        ffprobe, "-v", "error", "-select_streams", "v:0",
        "-show_entries", _ENTRIES, "-of", "json", "--", str(path),
    ]  # fmt: skip


def _number(*candidates: object) -> float | None:
    """First candidate that parses as a finite number ('N/A' and missing values are skipped)."""
    for value in candidates:
        try:
            number = float(str(value))
        except ValueError:
            continue
        if math.isfinite(number):  # rejects NaN and infinity
            return number
    return None


def _dimension(stream: dict[str, Any], key: str, name: str) -> int:
    value = stream.get(key)
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise DecodeError(key="error.decode.probe_failed", name=name)
    return value


def parse_probe(text: str, name: str = "") -> VideoInfo:
    """Turn ffprobe's JSON into a VideoInfo, or raise DecodeError for unusable output."""
    try:
        data = json.loads(text)
        streams = data["streams"]
        container = data.get("format", {})
    except (ValueError, KeyError, TypeError, AttributeError):
        raise DecodeError(key="error.decode.probe_failed", name=name) from None
    if not isinstance(streams, list) or not streams:
        raise DecodeError(key="error.decode.no_video", name=name)
    stream = streams[0]
    width, height = _dimension(stream, "width", name), _dimension(stream, "height", name)
    duration = _number(stream.get("duration"), container.get("duration"))
    if duration is None or duration <= 0:
        raise DecodeError(key="error.decode.no_duration", name=name)
    start = _number(stream.get("start_time"), container.get("start_time")) or 0.0
    return VideoInfo(width, height, duration, start)


def probe_video(path: Path, timeout_s: float = PROBE_TIMEOUT_S) -> VideoInfo:
    """Inspect a validated film path with ffprobe (bounded time and output)."""
    argv = probe_argv(find_tool("ffprobe"), path)
    try:
        done = subprocess.run(
            argv, check=False, capture_output=True, timeout=timeout_s, stdin=subprocess.DEVNULL
        )
    except subprocess.TimeoutExpired:
        raise DecodeError(key="error.decode.probe_failed", name=path.name) from None
    if done.returncode != 0 or len(done.stdout) > PROBE_MAX_OUTPUT_BYTES:
        detail = scrub_stderr(done.stderr, path, STDERR_LIMIT_BYTES)
        raise DecodeError(detail, key="error.decode.probe_failed", name=path.name)
    return parse_probe(done.stdout.decode("utf-8", errors="replace"), path.name)
