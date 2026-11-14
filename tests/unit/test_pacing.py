"""Pacing: cut rate over the film and its flat stretches."""

import numpy as np

from filmanalyser.analysis.pacing import analyse_pacing
from filmanalyser.analysis.timeline import build_timeline
from filmanalyser.core import features as f
from filmanalyser.core.config import PACING_PLATEAU_MIN_CHUNKS
from tests.fixtures.timelines import timeline


def _alternating(count: int, low: float = 1.0, high: float = 9.0) -> np.ndarray:
    return np.where(np.arange(count) % 2 == 0, low, high)


def _film_with_flat_stretch(first: int, last: int) -> np.ndarray:
    cuts = _alternating(100)
    cuts[first : last + 1] = 5.0
    return cuts


def test_the_rate_is_cuts_and_gradual_transitions_per_minute() -> None:
    cols = timeline(3, {f.CUT_COUNT: np.array([2.0, 4.0, 6.0]), f.GRADUAL_COUNT: 1.0})
    pacing = analyse_pacing(build_timeline(cols))
    assert pacing.rate_per_min == (3.0, 5.0, 7.0)
    assert pacing.mean_rate == 5.0


def test_a_flat_stretch_is_found_with_its_exact_span() -> None:
    cols = timeline(100, {f.CUT_COUNT: _film_with_flat_stretch(30, 44)})
    plateaus = analyse_pacing(build_timeline(cols)).plateaus
    assert len(plateaus) == 1
    flat = plateaus[0]
    assert (flat.first_chunk, flat.last_chunk) == (30, 44)
    assert (flat.start_s, flat.end_s) == (1800.0, 2700.0)
    assert flat.mean_rate == 6.0  # 5 cuts plus the baseline 1 gradual per minute


def test_two_separate_flat_stretches_are_two_plateaus() -> None:
    cuts = _alternating(120)
    cuts[10:20] = 5.0
    cuts[70:85] = 5.2
    plateaus = analyse_pacing(build_timeline(timeline(120, {f.CUT_COUNT: cuts}))).plateaus
    assert [(p.first_chunk, p.last_chunk) for p in plateaus] == [(10, 19), (70, 84)]


def test_a_stretch_shorter_than_the_minimum_is_not_a_plateau() -> None:
    cuts = _alternating(100)
    cuts[40 : 40 + PACING_PLATEAU_MIN_CHUNKS - 1] = 5.0
    assert analyse_pacing(build_timeline(timeline(100, {f.CUT_COUNT: cuts}))).plateaus == ()


def test_a_film_that_alternates_throughout_has_no_plateau() -> None:
    cols = timeline(100, {f.CUT_COUNT: _alternating(100)})
    assert analyse_pacing(build_timeline(cols)).plateaus == ()


def test_a_perfectly_flat_film_is_one_plateau_from_end_to_end() -> None:
    plateaus = analyse_pacing(build_timeline(timeline(40))).plateaus
    assert len(plateaus) == 1
    assert (plateaus[0].start_s, plateaus[0].end_s) == (0.0, 2400.0)


def test_a_film_too_short_for_a_plateau_has_none() -> None:
    assert analyse_pacing(build_timeline(timeline(PACING_PLATEAU_MIN_CHUNKS - 1))).plateaus == ()
    assert analyse_pacing(build_timeline(timeline(0))).plateaus == ()


def test_pacing_needs_no_audio() -> None:
    cols = timeline(100, {f.CUT_COUNT: _film_with_flat_stretch(30, 44)}, audio=False)
    assert len(analyse_pacing(build_timeline(cols)).plateaus) == 1


def test_the_same_input_gives_identical_output() -> None:
    tl = build_timeline(timeline(100, {f.CUT_COUNT: _film_with_flat_stretch(30, 44)}))
    assert analyse_pacing(tl) == analyse_pacing(tl)
