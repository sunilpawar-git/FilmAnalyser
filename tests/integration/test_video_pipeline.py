"""End to end on a clip with known hard cuts: the decoder, the extractors, the registry-driven
runner and the store, then the report. Precision and recall are measured against the ground truth
the clip was built from (the cut times), within one analysis frame."""

from pathlib import Path

import numpy as np
import pytest

from filmanalyser.core.chunk import Chunk
from filmanalyser.core.config import Config
from filmanalyser.extractors.registry import discover
from filmanalyser.extractors.shot_cuts import cut_positions
from filmanalyser.media.ffmpeg_stream import decode_chunks
from filmanalyser.pipeline.runner import analyse
from filmanalyser.report.renderer import render_report
from filmanalyser.report.resources.colors import ColorTokens
from filmanalyser.report.resources.strings import Strings
from filmanalyser.report.viewmodel import build_view
from tests.fixtures.make_synthetic import cut_times, make_cut_clip

SCENES = [("red", 3.0), ("green", 2.5), ("blue", 4.0), ("white", 3.5)]
CONFIG = Config(chunk_seconds=4.0, overlap_seconds=1.0, analysis_fps=12.0, frame_width=64)
TOLERANCE_S = 1 / 12  # one analysis frame


def _detected_times(film: Path) -> list[float]:
    times: list[float] = []
    for chunk in decode_chunks(film, CONFIG):
        assert isinstance(chunk, Chunk)
        for position in cut_positions(chunk.frames, chunk.context_frames):
            times.append(chunk.first_frame_s + position / chunk.fps)
    return times


def test_detected_cuts_match_the_ground_truth_within_one_frame(tmp_path: Path) -> None:
    film = make_cut_clip(tmp_path / "cuts.mp4", SCENES, fps=12)
    truth = cut_times(SCENES, 12)
    found = _detected_times(film)
    matched_truth = [t for t in truth if any(abs(f - t) <= TOLERANCE_S for f in found)]
    matched_found = [f for f in found if any(abs(f - t) <= TOLERANCE_S for t in truth)]
    assert len(matched_truth) == len(truth) == 3
    assert len(matched_found) == len(found) == 3  # precision 1.0 and recall 1.0


# Cuts that fall between analysis samples (the 12 fps grid), at source rates that are not 12 fps.
OFF_GRID = [
    (24, [("red", 1.875), ("blue", 2.625), ("black", 1.5), ("white", 2.125), ("green", 3.0)]),
    (25, [("red", 2.36), ("green", 2.6), ("blue", 3.92), ("white", 1.8)]),
]


@pytest.mark.parametrize(("fps", "scenes"), OFF_GRID)
def test_precision_and_recall_hold_for_cuts_between_samples(
    tmp_path: Path, fps: int, scenes: list[tuple[str, float]]
) -> None:
    film = make_cut_clip(tmp_path / "cuts.mp4", scenes, fps=fps)
    truth, found = cut_times(scenes, fps), _detected_times(film)
    assert len(found) == len(truth), (found, truth)
    for time in truth:  # every cut found within one analysis frame, and none spurious
        assert any(abs(f - time) <= TOLERANCE_S for f in found), (time, found)
    for time in found:
        assert any(abs(time - t) <= TOLERANCE_S for t in truth), (time, truth)


def test_the_runner_stores_every_declared_feature_and_the_count_of_cuts(tmp_path: Path) -> None:
    # The cut clip has no audio track, so the audio extractors are dropped (DECISIONS #64) and
    # every other declared feature is stored.
    film = make_cut_clip(tmp_path / "cuts.mp4", SCENES, fps=12)
    store = analyse(film, tmp_path / "out", CONFIG)
    columns = store.read_columns()
    assert store.complete
    assert int(np.asarray(columns["shot_cuts.cuts"], dtype=np.float64).sum()) == 3
    for extractor in discover():
        if extractor.needs_audio:
            assert f"{extractor.name}.{extractor.features[0]}" not in columns
            continue
        for feature in extractor.features:
            assert f"{extractor.name}.{feature}" in columns


def test_the_report_shows_the_stored_cut_count(tmp_path: Path) -> None:
    film = make_cut_clip(tmp_path / "cuts.mp4", SCENES, fps=12)
    store = analyse(film, tmp_path / "out", CONFIG)
    view = build_view(store.read_columns(), film=film.name)
    page = render_report(view, Strings.load(), ColorTokens.load())
    assert view.total_cuts == 3
    assert np.isclose(view.film_seconds, sum(s for _c, s in SCENES), atol=0.2)
    assert "<polyline" in page


def test_observers_see_every_chunk_decoded_then_stored_in_order(tmp_path: Path) -> None:
    film = make_cut_clip(tmp_path / "cuts.mp4", SCENES, fps=12)
    events: list[tuple[str, int]] = []
    analyse(
        film,
        tmp_path / "out",
        CONFIG,
        on_decoded=lambda i: events.append(("decoded", i)),
        on_stored=lambda i: events.append(("stored", i)),
    )
    chunks = len(list(decode_chunks(film, CONFIG)))
    expected = [step for i in range(chunks) for step in (("decoded", i), ("stored", i))]
    assert events == expected
