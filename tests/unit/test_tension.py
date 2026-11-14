"""Tension: one smoothed series from cut rate and loudness, and its peak."""

import numpy as np
import pytest

from filmanalyser.analysis.tension import analyse_tension
from filmanalyser.analysis.timeline import build_timeline
from filmanalyser.core import features as f
from tests.fixtures.timelines import timeline


def _bump(count: int, centre: int, height: float, base: float, width: float = 2.0) -> np.ndarray:
    return base + height * np.exp(-(((np.arange(count) - centre) / width) ** 2))


def test_the_peak_is_where_cutting_and_loudness_peak_together() -> None:
    cols = timeline(
        100,
        {f.CUT_COUNT: _bump(100, 72, 12.0, 2.0), f.LUFS: _bump(100, 72, 15.0, -35.0)},
    )
    tension = analyse_tension(build_timeline(cols))
    assert tension.peak is not None
    assert abs(tension.peak.chunk - 72) <= 1
    assert tension.peak.start_s == tension.peak.chunk * 60.0
    assert tension.peak.end_s == tension.peak.start_s + 60.0
    assert tension.components == (f.CUT_RATE, f.LUFS)
    assert len(tension.values) == 100


def test_the_peak_value_is_the_maximum_of_the_series() -> None:
    cols = timeline(
        100, {f.CUT_COUNT: _bump(100, 40, 10.0, 2.0), f.LUFS: _bump(100, 40, 12.0, -35.0)}
    )
    tension = analyse_tension(build_timeline(cols))
    assert tension.peak is not None
    assert tension.peak.value == max(tension.values)


def test_a_film_without_audio_uses_cut_rate_alone_and_says_so() -> None:
    cols = timeline(100, {f.CUT_COUNT: _bump(100, 55, 10.0, 2.0)}, audio=False)
    tension = analyse_tension(build_timeline(cols))
    assert tension.components == (f.CUT_RATE,)
    assert tension.peak is not None and abs(tension.peak.chunk - 55) <= 1


def test_a_flat_film_has_no_peak() -> None:
    tension = analyse_tension(build_timeline(timeline(60)))
    assert tension.peak is None
    assert set(tension.values) == {0.0}


@pytest.mark.parametrize("seed", range(40))
def test_noise_has_no_peak(seed: int) -> None:
    rng = np.random.default_rng(seed)
    cols = timeline(120, {f.CUT_COUNT: rng.normal(5.0, 1.0, 120)}, audio=False)
    assert analyse_tension(build_timeline(cols)).peak is None


def test_a_silent_stretch_is_not_scored_as_calm_or_loud() -> None:
    lufs = _bump(100, 60, 10.0, -35.0)
    lufs[20:30] = -70.0
    tension = analyse_tension(
        build_timeline(timeline(100, {f.LUFS: lufs, f.CUT_COUNT: _bump(100, 60, 12.0, 2.0)}))
    )
    assert all(np.isfinite(tension.values))
    assert tension.peak is not None and abs(tension.peak.chunk - 60) <= 1


def test_an_empty_film_has_an_empty_series_and_no_peak() -> None:
    tension = analyse_tension(build_timeline(timeline(0)))
    assert tension.values == () and tension.peak is None


def test_the_same_input_gives_identical_output() -> None:
    tl = build_timeline(timeline(100, {f.CUT_COUNT: _bump(100, 40, 10.0, 2.0)}))
    assert analyse_tension(tl) == analyse_tension(tl)
