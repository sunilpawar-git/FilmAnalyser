"""Deterministic synthetic clips from ffmpeg's lavfi sources (no copyrighted film in the repo).

Ground truth is known by construction: every frame's luma is a sawtooth of its own timestamp
(`RAMP_PERIOD_S` seconds per tooth), so frame order, timing and chunk continuity can be asserted
without a reference decoder.
"""

import shutil
import subprocess
from collections.abc import Sequence
from pathlib import Path

VIDEO_ENCODE = ["-c:v", "libx264", "-preset", "ultrafast", "-crf", "18", "-pix_fmt", "yuv420p"]
RAMP_PERIOD_S = 8.0  # luma climbs 0 -> 255 over this many seconds, then wraps
SIZE = (320, 180)
FPS = 10


def ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None


def clip_argv(
    out: Path, seconds: float, *, size: tuple[int, int] = SIZE, fps: int = FPS, offset: float = 0.0
) -> list[str]:
    width, height = size
    ramp = f"geq=lum='255*mod(T,{RAMP_PERIOD_S})/{RAMP_PERIOD_S}':cb=128:cr=128"
    source = f"color=c=black:s={width}x{height}:r={fps}:d={seconds},{ramp}"
    return [
        "ffmpeg", "-v", "error", "-y",
        "-f", "lavfi", "-i", source,
        "-f", "lavfi", "-i", f"sine=frequency=440:sample_rate=16000:duration={seconds}",
        *VIDEO_ENCODE, "-g", str(fps * 2), "-c:a", "aac", "-b:a", "32k", "-shortest",
        "-output_ts_offset", str(offset),
        "--", str(out),
    ]  # fmt: skip


def make_clip(
    out: Path, seconds: float, *, size: tuple[int, int] = SIZE, fps: int = FPS, offset: float = 0.0
) -> Path:
    """Write an mp4 of `seconds` seconds; `offset` shifts every timestamp (non-zero start_time)."""
    subprocess.run(clip_argv(out, seconds, size=size, fps=fps, offset=offset), check=True)
    return out


def concat_clip(base: Path, out: Path, times: int) -> Path:
    """`base` repeated `times` times, by stream copy (fast): a longer film with the same content."""
    listing = out.with_suffix(".txt")
    listing.write_text("".join(f"file '{base}'\n" for _ in range(times)), encoding="utf-8")
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(listing),
         "-c", "copy", "--", str(out)],
        check=True,
    )  # fmt: skip
    return out


def _whole_frames(seconds: float, fps: int) -> int:
    """ffmpeg rounds a scene's duration UP to whole frames, so the ground truth is only exact when a
    duration is already a whole number of frames. Anything else is refused, never silently wrong."""
    frames = seconds * fps
    if abs(frames - round(frames)) > 1e-9:
        raise ValueError(f"{seconds} s is not a whole number of frames at {fps} fps")
    return round(frames)


def cut_clip_argv(
    out: Path, scenes: Sequence[tuple[str, float]], *, size: tuple[int, int] = SIZE, fps: int = FPS
) -> list[str]:
    """A clip of flat colour scenes joined by hard cuts. `scenes` is (ffmpeg colour, seconds); each
    duration must be a whole number of frames at `fps` (see `_whole_frames`)."""
    width, height = size
    inputs: list[str] = []
    for colour, seconds in scenes:
        _whole_frames(seconds, fps)
        source = f"color=c={colour}:s={width}x{height}:r={fps}:d={seconds}"
        inputs += ["-f", "lavfi", "-i", source]
    return [
        "ffmpeg", "-v", "error", "-y", *inputs,
        "-filter_complex", f"concat=n={len(scenes)}:v=1:a=0",
        *VIDEO_ENCODE, "-g", str(fps * 2), "--", str(out),
    ]  # fmt: skip


def cut_times(scenes: Sequence[tuple[str, float]], fps: int = FPS) -> list[float]:
    """Ground truth: the film time of every hard cut (the end of every scene but the last), in whole
    frames at `fps`, so it matches the clip exactly."""
    times, frames = [], 0
    for _colour, seconds in scenes[:-1]:
        frames += _whole_frames(seconds, fps)
        times.append(frames / fps)
    return times


def make_cut_clip(
    out: Path, scenes: Sequence[tuple[str, float]], *, size: tuple[int, int] = SIZE, fps: int = FPS
) -> Path:
    subprocess.run(cut_clip_argv(out, scenes, size=size, fps=fps), check=True)
    return out
