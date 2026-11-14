"""The timeline: store columns in, one aligned set of series out. Missing values stay missing."""

import numpy as np
import pytest

from filmanalyser.analysis.timeline import build_timeline, film_state, smooth, zscores
from filmanalyser.core import features as f
from filmanalyser.core.config import LOUDNESS_ABS_GATE_LUFS
from filmanalyser.core.errors import AnalysisError
from tests.fixtures.timelines import AUDIO, VIDEO, timeline


def test_cut_rate_counts_cuts_and_gradual_transitions_per_minute() -> None:
    cols = timeline(4, {f.CUT_COUNT: np.array([6.0, 0, 3, 12]), f.GRADUAL_COUNT: 2.0})
    tl = build_timeline(cols)
    assert list(tl.series[f.CUT_RATE]) == [8.0, 2.0, 5.0, 14.0]


def test_cut_rate_is_per_minute_whatever_the_chunk_length() -> None:
    cols = timeline(3, {f.CUT_COUNT: 5.0, f.GRADUAL_COUNT: 0.0})
    for name in (f.START_S, f.END_S):
        cols[name] = np.asarray(cols[name], dtype=np.float64) / 2  # 30 s chunks
    tl = build_timeline(cols)
    assert list(tl.series[f.CUT_RATE]) == [10.0, 10.0, 10.0]


def test_loudness_at_the_floor_is_missing_not_a_value() -> None:
    lufs = np.array([-20.0, LOUDNESS_ABS_GATE_LUFS, -22.0, -75.0])
    tl = build_timeline(timeline(4, {f.LUFS: lufs}))
    got = tl.series[f.LUFS]
    assert got[0] == -20.0
    assert np.isnan(got[1]) and np.isnan(got[3])


def test_series_are_read_only() -> None:
    tl = build_timeline(timeline(4))
    with pytest.raises(ValueError, match="read-only"):
        tl.series[f.CUT_RATE][0] = 1.0


def test_audio_used_follows_the_columns() -> None:
    assert build_timeline(timeline(6)).audio_used is True
    assert build_timeline(timeline(6, audio=False)).audio_used is False


def test_state_names_are_the_columns_the_film_has_in_a_fixed_order() -> None:
    with_audio = build_timeline(timeline(6)).state_names
    assert with_audio == (f.CUT_RATE, *AUDIO, *VIDEO)
    assert build_timeline(timeline(6, audio=False)).state_names == (f.CUT_RATE, *VIDEO)


def test_a_short_last_chunk_is_dropped_but_the_film_still_ends_there() -> None:
    tl = build_timeline(timeline(5, last_s=10.0))
    assert tl.count == 4
    assert tl.film_end_s == 4 * 60.0 + 10.0


def test_a_last_chunk_of_normal_length_is_kept() -> None:
    tl = build_timeline(timeline(5, last_s=45.0))
    assert tl.count == 5
    assert tl.film_end_s == 4 * 60.0 + 45.0


def test_an_empty_store_is_an_empty_timeline() -> None:
    cols = timeline(0)
    tl = build_timeline(cols)
    assert tl.count == 0 and tl.film_end_s == 0.0


@pytest.mark.parametrize("missing", [f.START_S, f.END_S, f.CUT_COUNT, f.GRADUAL_COUNT])
def test_a_required_column_must_exist(missing: str) -> None:
    cols = timeline(6)
    del cols[missing]
    with pytest.raises(AnalysisError) as info:
        build_timeline(cols)
    assert info.value.key == "error.analysis.bad_timeline"
    assert info.value.fields == {"name": missing}


def test_columns_of_different_length_are_rejected() -> None:
    cols = timeline(6)
    cols[f.BRIGHTNESS] = cols[f.BRIGHTNESS][:4]
    with pytest.raises(AnalysisError):
        build_timeline(cols)


def test_times_must_be_finite_and_increasing() -> None:
    cols = timeline(6)
    cols[f.END_S] = cols[f.START_S].copy()
    with pytest.raises(AnalysisError):
        build_timeline(cols)


def test_zscores_have_zero_mean_and_unit_spread() -> None:
    z = zscores(np.array([1.0, 2.0, 3.0, 4.0, 10.0]))
    assert abs(float(z.mean())) < 1e-12
    assert abs(float(z.std()) - 1.0) < 1e-12


def test_a_constant_series_scores_zero() -> None:
    assert list(zscores(np.full(5, 7.0))) == [0.0] * 5


def test_zscores_ignore_missing_values_and_keep_them_missing() -> None:
    z = zscores(np.array([1.0, np.nan, 3.0, 5.0]))
    assert np.isnan(z[1])
    assert abs(float(np.nanmean(z))) < 1e-12


def test_a_series_with_one_value_scores_zero() -> None:
    assert list(zscores(np.array([np.nan, 4.0]))[1:]) == [0.0]


def test_smoothing_is_a_centred_moving_average_truncated_at_the_ends() -> None:
    got = smooth(np.array([0.0, 3.0, 0.0, 6.0, 0.0]), 3)
    assert list(got) == [1.5, 1.0, 3.0, 2.0, 3.0]


def test_smoothing_with_width_one_changes_nothing() -> None:
    x = np.array([1.0, 5.0, 2.0])
    assert list(smooth(x, 1)) == list(x)


def test_smoothing_skips_missing_values() -> None:
    got = smooth(np.array([2.0, np.nan, 4.0]), 3)
    assert list(got) == [2.0, 3.0, 4.0]


def test_smoothing_leaves_a_fully_missing_window_missing() -> None:
    got = smooth(np.array([np.nan, np.nan, np.nan, 1.0]), 3)
    assert np.isnan(got[0]) and np.isnan(got[1]) and got[3] == 1.0


def test_film_state_has_one_smoothed_z_column_per_state_name() -> None:
    tl = build_timeline(timeline(12, {f.CUT_COUNT: np.arange(12.0)}))
    names, matrix = film_state(tl, 1)
    assert names == tl.state_names
    assert matrix.shape == (12, len(names))
    assert abs(float(matrix[:, 0].mean())) < 1e-12
