"""Deterministic synthetic clips from ffmpeg's lavfi sources (no copyrighted film in the repo).

Ground truth is known by construction: every frame's luma is a sawtooth of its own timestamp
(`RAMP_PERIOD_S` seconds per tooth), so frame order, timing and chunk continuity can be asserted
without a reference decoder.
"""

import shutil
import subprocess
from pathlib import Path

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
        "-c:v", "libx264", "-preset", "ultrafast", "-crf", "18", "-pix_fmt", "yuv420p",
        "-g", str(fps * 2), "-c:a", "aac", "-b:a", "32k", "-shortest",
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
