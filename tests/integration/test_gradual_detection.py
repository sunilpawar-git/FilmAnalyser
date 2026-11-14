"""The gradual detector on a real encoded clip with a dissolve at a known time (DECISIONS #79).

The clip is two synthetic colour scenes joined by a one-second dissolve from 3 s to 4 s, built by
ffmpeg's xfade filter, so the transition's start and end are known exactly. No real footage."""

import subprocess
from pathlib import Path

from filmanalyser.core.config import Config
from filmanalyser.extractors.shot_cuts import frame_distances, segment
from filmanalyser.media.ffmpeg_stream import decode_chunks


def _dissolve_clip(out: Path) -> Path:
    """Two textured scenes (test pattern, fractal) cross-dissolved over one second. Flat colours
    would be pathological: a flat frame's histogram is concentrated, so any change is huge."""
    graph = (
        "[0:v]trim=0:3,setpts=PTS-STARTPTS[a];[1:v]trim=0:3,setpts=PTS-STARTPTS[b];"
        "[a][b]xfade=transition=fade:duration=1:offset=2,format=yuv420p[v]"
    )
    subprocess.run(
        [
            "ffmpeg", "-v", "error", "-y",
            "-f", "lavfi", "-i", "testsrc2=s=160x90:r=12:d=3",
            "-f", "lavfi", "-i", "mandelbrot=s=160x90:r=12",
            "-filter_complex", graph, "-map", "[v]",
            "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", "--", str(out),
        ],
        check=True,
    )  # fmt: skip
    return out


def test_a_dissolve_is_found_as_one_gradual_transition_with_no_cut(tmp_path: Path) -> None:
    clip = _dissolve_clip(tmp_path / "dissolve.mp4")
    cuts: list[float] = []
    spans: list[tuple[float, float]] = []
    for chunk in decode_chunks(clip, Config(chunk_seconds=6.0, overlap_seconds=0.5)):
        seg = segment(frame_distances(chunk.frames), chunk.context_frames)
        cuts += [chunk.first_frame_s + k / chunk.fps for k in seg.cuts]
        spans += [(chunk.first_frame_s + a / chunk.fps, chunk.first_frame_s + b / chunk.fps)
                  for a, b in seg.gradual]  # fmt: skip
    assert cuts == []
    assert len(spans) == 1
    start, end = spans[0]
    assert abs(start - 2.0) <= 0.25 and abs(end - 3.0) <= 0.25  # the dissolve is 2 s to 3 s
