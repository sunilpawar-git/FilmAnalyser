"""Shot cuts: precision and recall against known ground truth, and the chunk-boundary rules
(no duplicate and no missed cut where a chunk meets its predecessor). Frames are built in memory."""

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from filmanalyser.core.chunk import Chunk, Frames
from filmanalyser.core.config import Config
from filmanalyser.extractors.shot_cuts import EXTRACTOR, ShotCuts, cut_positions
from filmanalyser.media.chunker import chunk_frames

FPS = 10.0
SHAPE = (4, 4)
TOLERANCE_FRAMES = 1  # a detected cut counts as correct within one analysis frame (0.1 s)


def scene(colour: tuple[int, int, int], frames: int) -> Frames:
    return np.broadcast_to(np.array(colour, dtype=np.uint8), (frames, *SHAPE, 3)).copy()


def stream(scenes: list[tuple[tuple[int, int, int], int]]) -> Frames:
    return np.concatenate([scene(colour, n) for colour, n in scenes])


def ramp(frames: int) -> Frames:
    levels = np.linspace(0, 255, frames).astype(np.uint8)
    return np.broadcast_to(levels[:, None, None, None], (frames, *SHAPE, 3)).copy()


def test_a_still_scene_has_no_cuts() -> None:
    assert cut_positions(scene((90, 120, 60), 30), context_frames=0) == ()


def test_a_hard_cut_is_found_on_the_frame_where_the_new_scene_starts() -> None:
    frames = stream([((255, 0, 0), 5), ((0, 0, 255), 5)])
    assert cut_positions(frames, context_frames=0) == (5,)


def test_a_gradual_brightness_ramp_is_not_a_cut() -> None:
    assert cut_positions(ramp(120), context_frames=0) == ()


def test_precision_and_recall_are_perfect_on_known_cuts() -> None:
    layout = [((255, 0, 0), 30), ((0, 255, 0), 25), ((0, 0, 255), 40), ((255, 255, 255), 35)]
    truth = [30, 55, 95]  # frame index where each new scene starts
    found = cut_positions(stream(layout), context_frames=0)
    matched = {t for t in truth if any(abs(f - t) <= TOLERANCE_FRAMES for f in found)}
    precision = len(matched) / len(found)
    recall = len(matched) / len(truth)
    assert (precision, recall) == (1.0, 1.0)
    assert len(found) == len(truth)


def test_one_step_of_brightness_is_not_a_cut() -> None:
    """Soft binning: a one-level change moves the histogram a fraction of a bin, not a whole one."""
    frames = np.concatenate([scene((130, 130, 130), 5), scene((131, 131, 131), 5)])
    assert cut_positions(frames, context_frames=0) == ()


def chunk_for(frames: Frames, index: int, context: int) -> Chunk:
    return Chunk(index, 0.0, len(frames) / FPS, FPS, frames, context_frames=context)


def test_extract_reports_cuts_in_the_core_and_the_largest_change() -> None:
    frames = stream([((255, 0, 0), 4), ((0, 0, 255), 4)])
    features = ShotCuts().extract(chunk_for(frames, index=0, context=0))
    assert features["cuts"] == 1.0
    assert features["max_diff"] == pytest.approx(1.0)


def test_a_cut_inside_the_overlap_is_not_counted_again_by_the_next_chunk() -> None:
    # The first chunk's context ends on the new scene: the cut belongs to the core of chunk 0.
    frames = stream([((255, 0, 0), 6), ((0, 0, 255), 6)])
    first = chunk_for(frames[:8], index=0, context=0)
    second = chunk_for(frames[4:], index=1, context=4)  # overlap begins at frame 4
    assert ShotCuts().extract(first)["cuts"] == 1.0
    assert ShotCuts().extract(second)["cuts"] == 0.0


def test_a_cut_on_the_first_core_frame_is_counted_once_in_its_own_chunk() -> None:
    """The boundary case a missed-cut bug would hit: the new scene starts exactly at the chunk's
    first core frame, so the only comparison that finds it crosses the overlap."""
    frames = stream([((255, 0, 0), 4), ((0, 0, 255), 4)])
    assert ShotCuts().extract(chunk_for(frames, index=1, context=4))["cuts"] == 1.0


def test_extractor_is_registered_under_its_feature_names() -> None:
    assert EXTRACTOR.name == "shot_cuts"
    assert EXTRACTOR.features == ("cuts", "gradual", "max_diff")


def _whole_and_chunked(
    scenes: list[int], per_chunk: int, overlap: int
) -> tuple[tuple[int, ...], int, float]:
    frames = stream([((i * 60 % 256, i * 97 % 256, i * 31 % 256), n) for i, n in enumerate(scenes)])
    config = Config(
        chunk_seconds=per_chunk / FPS,
        overlap_seconds=overlap / FPS,
        analysis_fps=FPS,
        frame_width=4,
    )
    whole = cut_positions(frames, context_frames=0)
    cuts = 0
    max_diff = 0.0
    for chunk in chunk_frames([*frames], config, SHAPE):
        features = ShotCuts().extract(chunk)
        cuts += int(features["cuts"])
        max_diff = max(max_diff, features["max_diff"])
    return whole, cuts, max_diff


@settings(max_examples=60, deadline=None)
@given(
    scenes=st.lists(st.integers(3, 25), min_size=2, max_size=6),
    per_chunk=st.integers(4, 30),
    overlap=st.integers(1, 3),
)
def test_chunking_never_adds_or_loses_a_cut(
    scenes: list[int], per_chunk: int, overlap: int
) -> None:
    """Improvement 4: for any chunk size and any overlap of at least one frame, the cuts found
    chunk by chunk are exactly the cuts found on the whole film."""
    if overlap >= per_chunk:
        overlap = per_chunk - 1
    whole, cuts, _ = _whole_and_chunked(scenes, per_chunk, overlap)
    assert cuts == len(whole)
