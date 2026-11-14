"""Act breaks on synthetic timelines with known change points (no ffmpeg, no files)."""

from dataclasses import replace
from typing import Any

import numpy as np
import pytest

from filmanalyser.analysis.act_breaks import ActBreaks, ActSettings, change_scores, find_act_breaks
from filmanalyser.analysis.timeline import Columns, build_timeline
from filmanalyser.core import features as f
from filmanalyser.core.config import (
    ACT_MAX_BREAKS,
    ACT_MIN_GAP_CHUNKS,
    ACT_TIE_FRACTION,
    ACT_WINDOW_CHUNKS,
    ACT_ZONE_1,
    ACT_ZONE_2,
    ACT_ZONE_PRIORS,
)
from tests.fixtures.timelines import AUDIO, VIDEO, block_film, blocks, noise_film, timeline


def _breaks(cols: Columns, **settings: Any) -> ActBreaks:
    return find_act_breaks(build_timeline(cols), replace(ActSettings(), **settings))


def _at(result: ActBreaks) -> list[int]:
    return [b.boundary for b in result.breaks]


def test_three_blocks_give_two_breaks_at_the_block_edges() -> None:
    result = _breaks(block_film([25, 50, 25], [1.0, 3.0, 1.0]))
    assert len(result.breaks) == 2
    assert abs(result.breaks[0].boundary - 25) <= 1
    assert abs(result.breaks[1].boundary - 75) <= 1
    assert result.empty_zones == ()


def test_break_times_come_from_the_container_clock() -> None:
    result = _breaks(block_film([25, 50, 25], [1.0, 3.0, 1.0]))
    for brk in result.breaks:
        assert brk.time_s == brk.boundary * 60.0


def test_acts_are_contiguous_time_spans_covering_the_film() -> None:
    result = _breaks(block_film([25, 50, 25], [1.0, 3.0, 1.0]))
    assert len(result.acts) == 3
    assert result.acts[0].start_s == 0.0
    assert result.acts[-1].end_s == 6000.0
    for before, after in zip(result.acts, result.acts[1:], strict=False):
        assert before.end_s == after.start_s
    assert [a.end_s for a in result.acts[:-1]] == [b.time_s for b in result.breaks]


def test_the_last_act_ends_where_the_film_ends() -> None:
    cols = block_film([25, 50, 24], [1.0, 3.0, 1.0])
    cols[f.END_S][-1] -= 20.0  # the film ends 20 s early; the last chunk is still long enough
    assert _breaks(cols).acts[-1].end_s == cols[f.END_S][-1]


def test_modest_steps_of_a_staircase_stay_below_the_threshold() -> None:
    """Scores are relative to the film's own spread, so a film that climbs in equal stages has a
    large spread and each stage a modest score. Documented in LIMITATIONS: this is a miss, kept."""
    cols = block_film([25, 50, 25], [0.0, 3.0, 6.0])
    assert _breaks(cols).breaks == ()
    assert len(_breaks(cols, min_score=0.0).breaks) == 2


def test_one_step_gives_one_break_and_none_in_the_other_zone() -> None:
    result = _breaks(block_film([30, 70], [1.0, 3.0]))
    assert _at(result) == [30]
    assert result.empty_zones == (2,)


def test_a_step_in_the_second_zone_leaves_the_first_zone_empty() -> None:
    result = _breaks(block_film([70, 30], [1.0, 3.0]))
    assert _at(result) == [70]
    assert result.empty_zones == (1,)


def test_a_flat_film_has_no_breaks_and_says_both_zones_are_empty() -> None:
    result = _breaks(timeline(100))
    assert result.breaks == ()
    assert result.empty_zones == (1, 2)
    assert len(result.acts) == 1
    assert (result.acts[0].start_s, result.acts[0].end_s) == (0.0, 6000.0)


@pytest.mark.parametrize("seed", range(40))
def test_a_pure_noise_film_has_no_breaks(seed: int) -> None:
    assert _breaks(noise_film(120, seed)).breaks == ()


@pytest.mark.parametrize("seed", range(10))
def test_a_pure_noise_film_without_audio_has_no_breaks(seed: int) -> None:
    assert _breaks(noise_film(120, seed, audio=False)).breaks == ()


@pytest.mark.parametrize("step", [10, 13, 42, 50, 58, 93])
def test_a_change_outside_both_zones_is_not_reported(step: int) -> None:
    result = _breaks(block_film([step, 100 - step], [1.0, 3.0]))
    assert result.breaks == ()


@pytest.mark.parametrize("step", [16, 25, 39, 61, 75, 89])
def test_a_change_inside_a_zone_is_reported(step: int) -> None:
    assert _at(_breaks(block_film([step, 100 - step], [1.0, 3.0]))) == [step]


def test_a_change_in_one_feature_only_is_below_the_threshold() -> None:
    cols = timeline(100, {f.CUT_COUNT: blocks([30, 70], [1.0, 9.0])})
    result = _breaks(cols)
    assert result.breaks == ()
    only = _breaks(cols, min_score=0.0)
    assert _at(only) == [30]  # the step is there; it is simply below ACT_MIN_SCORE
    assert 0.0 < only.breaks[0].score < ActSettings().min_score


def test_the_threshold_is_the_setting_not_a_constant() -> None:
    cols = block_film([30, 70], [1.0, 3.0])
    score = _breaks(cols).breaks[0].score
    assert _breaks(cols, min_score=score + 0.01).breaks == ()
    assert _at(_breaks(cols, min_score=score - 0.01)) == [30]


def test_two_close_steps_give_one_break_the_stronger() -> None:
    gap = ACT_MIN_GAP_CHUNKS - 3
    cols = block_film([25, gap, 100 - 25 - gap], [0.0, 1.0, -2.0])
    result = _breaks(cols)
    assert _at(result) == [25 + gap]


def test_two_close_steps_the_other_way_round() -> None:
    gap = ACT_MIN_GAP_CHUNKS - 3
    cols = block_film([25, gap, 100 - 25 - gap], [0.0, 3.0, 2.0])
    assert _at(_breaks(cols)) == [25]


def test_a_stronger_change_just_outside_a_zone_absorbs_a_close_candidate_inside_it() -> None:
    """Merging comes before the zone choice (DECISIONS #90): the change at chunk 44 lies outside
    both zones and is the stronger, so it absorbs the in-zone candidate at 36."""
    cols = block_film([36, 8, 56], [0.0, 3.0, -2.0])
    assert _at(_breaks(cols, min_gap=1)) == [36]  # on its own, the in-zone candidate is a break
    assert _breaks(cols).breaks == ()


def test_a_second_step_outside_every_zone_adds_no_break() -> None:
    cols = block_film([20, 30, 50], [0.0, 3.0, 4.0])  # steps at 20 (zone 1) and 50 (in no zone)
    assert _at(_breaks(cols)) == [20]


def test_a_tie_goes_to_the_candidate_nearer_the_classical_position() -> None:
    low, high = (ACT_ZONE_PRIORS[0] - 0.05) * 100, (ACT_ZONE_PRIORS[0] + 0.07) * 100
    near_low = block_film([round(low), round(high) - round(low), 100 - round(high)], [0, 1, 0])
    assert _at(_breaks(near_low)) == [round(low)]
    low, high = (ACT_ZONE_PRIORS[0] - 0.07) * 100, (ACT_ZONE_PRIORS[0] + 0.05) * 100
    near_high = block_film([round(low), round(high) - round(low), 100 - round(high)], [0, 1, 0])
    assert _at(_breaks(near_high)) == [round(high)]


def test_a_clearly_stronger_candidate_beats_the_classical_position() -> None:
    cols = block_film([20, 12, 68], [0.0, 1.4, -0.6])  # the second step is the larger
    assert _at(_breaks(cols)) == [32]
    assert ACT_TIE_FRACTION < 0.5


def test_a_break_is_never_forced_where_nothing_changed() -> None:
    result = _breaks(timeline(100))
    assert result.breaks == ()
    assert ACT_MAX_BREAKS == 2


@pytest.mark.parametrize("count", [0, 1, 5, 2 * ACT_WINDOW_CHUNKS - 1])
def test_a_film_shorter_than_two_windows_has_no_breaks_and_no_error(count: int) -> None:
    result = _breaks(block_film([count // 2, count - count // 2], [1.0, 3.0]))
    assert result.breaks == ()
    assert result.scored == 0


def test_a_film_of_exactly_two_windows_can_be_scored_once() -> None:
    result = _breaks(block_film([5, 5], [1.0, 3.0]))
    assert result.scored == 1
    assert result.breaks == ()  # the boundary at 50% is in neither zone


def test_without_audio_the_breaks_come_from_video_features_alone() -> None:
    result = _breaks(block_film([25, 50, 25], [1.0, 3.0, 1.0], audio=False))
    assert result.audio_used is False
    assert set(result.features_used) == {f.CUT_RATE, *VIDEO}
    assert len(result.breaks) == 2
    assert not set(AUDIO) & {name for b in result.breaks for name in b.moved}


def test_with_audio_the_result_says_audio_was_used() -> None:
    result = _breaks(block_film([25, 50, 25], [1.0, 3.0, 1.0]))
    assert result.audio_used is True
    assert set(AUDIO) <= set(result.features_used)


def test_a_silent_stretch_does_not_read_as_a_loudness_drop() -> None:
    lufs = np.full(100, -25.0)
    lufs[18:30] = -70.0  # the loudness floor: silence, not a measurement
    assert _breaks(timeline(100, {f.LUFS: lufs}), min_score=0.0).breaks == ()
    as_a_value = np.where(lufs <= -70.0, -69.0, lufs)  # just above the floor: a real measurement
    assert _breaks(timeline(100, {f.LUFS: as_a_value}), min_score=0.3).breaks != ()


def test_a_real_loudness_drop_is_still_a_break() -> None:
    lufs = blocks([30, 70], [-25.0, -45.0])
    cols = block_film([30, 70], [1.0, 3.0])
    cols[f.LUFS] = lufs
    assert _at(_breaks(cols)) == [30]


def test_the_features_that_moved_most_are_named() -> None:
    cols = timeline(
        100,
        {
            f.CUT_COUNT: blocks([30, 70], [1.0, 9.0]),
            f.LUFS: blocks([30, 70], [-40.0, -20.0]),
            f.BRIGHTNESS: np.linspace(0.2, 0.4, 100),  # drifts, does not step
        },
    )
    result = _breaks(cols, min_score=0.0)
    brk = result.breaks[0]
    assert len(brk.moved) == 2
    assert set(brk.moved) == {f.CUT_RATE, f.LUFS}


def test_the_same_input_gives_identical_output() -> None:
    cols = block_film([25, 50, 25], [1.0, 3.0, 1.0])
    assert _breaks(cols) == _breaks(cols)
    noisy = noise_film(120, 3)
    assert _breaks(noisy) == _breaks(noisy)


def test_zones_are_those_in_the_config() -> None:
    assert ACT_ZONE_1[1] < ACT_ZONE_2[0]
    assert ACT_ZONE_1[0] < ACT_ZONE_PRIORS[0] < ACT_ZONE_1[1]
    assert ACT_ZONE_2[0] < ACT_ZONE_PRIORS[1] < ACT_ZONE_2[1]


def test_a_boundary_where_nothing_was_measured_on_both_sides_has_no_score() -> None:
    scores = change_scores(np.full((12, 3), np.nan), 5)
    assert not np.isfinite(scores).any()
