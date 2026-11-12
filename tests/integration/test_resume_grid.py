"""P3-1 (DECISIONS #54): a resumed decode must sample the same frames as an uninterrupted one, even
when the source frame rate is not a multiple of the analysis rate and the seek point falls between
source frames. Before the fix the 12 fps grid was anchored to the seek point, not to film time."""

from pathlib import Path

import numpy as np
import pytest

from filmanalyser.core.config import Config
from filmanalyser.media.ffmpeg_stream import decode_chunks
from tests.fixtures.make_synthetic import make_clip

# 10.25 s chunks at 12 fps: every resume point lies between the frames of a 25 or 30 fps source.
CONFIG = Config(chunk_seconds=10.25, overlap_seconds=1.0, analysis_fps=12.0, frame_width=64)


@pytest.mark.parametrize("source_fps", [25, 30])
def test_resumed_chunks_sample_the_same_frames_as_an_uninterrupted_run(
    source_fps: int, tmp_path: Path
) -> None:
    film = make_clip(tmp_path / f"source_{source_fps}.mp4", seconds=42, fps=source_fps)
    whole = list(decode_chunks(film, CONFIG))
    assert len(whole) >= 4  # enough resume points to matter
    for start in range(1, len(whole)):
        resumed = list(decode_chunks(film, CONFIG, start_chunk=start))
        assert [c.index for c in resumed] == list(range(start, len(whole)))
        for part, full in zip(resumed, whole[start:], strict=True):
            assert np.array_equal(part.frames, full.frames), (
                f"chunk {full.index} at {source_fps} fps"
            )
            assert part.start_s == full.start_s
