"""Flags: timestamped moments worth a look, each with the rule that raised it."""

import numpy as np

from filmanalyser.analysis.flags import Flag, FlagKind, find_flags
from filmanalyser.analysis.timeline import Columns, build_timeline
from filmanalyser.core import features as f
from filmanalyser.core.config import FLAG_NO_CUT_CHUNKS
from tests.fixtures.timelines import timeline


def _flags(cols: Columns) -> list[Flag]:
    return list(find_flags(build_timeline(cols)))


def _of(flags: list[Flag], kind: FlagKind) -> list[Flag]:
    return [x for x in flags if x.kind is kind]


def _with(count: int, name: str, at: slice, value: float, base: float) -> dict[str, np.ndarray]:
    series = np.full(count, base)
    series[at] = value
    return {name: series}


def test_a_flat_film_raises_nothing() -> None:
    assert _flags(timeline(100)) == []


def test_a_burst_of_fast_cutting_is_one_flag_over_its_chunks() -> None:
    cols = timeline(100, _with(100, f.CUT_COUNT, slice(40, 42), 20.0, 2.0))
    (flag,) = _of(_flags(cols), FlagKind.FAST_CUTTING)
    assert (flag.first_chunk, flag.last_chunk) == (40, 41)
    assert (flag.start_s, flag.end_s) == (2400.0, 2520.0)
    assert flag.value > 2.0  # z above the film


def test_a_loudness_spike_is_flagged() -> None:
    cols = timeline(100, _with(100, f.LUFS, slice(70, 71), -8.0, -25.0))
    (flag,) = _of(_flags(cols), FlagKind.LOUD)
    assert (flag.first_chunk, flag.start_s) == (70, 4200.0)


def test_a_near_silent_chunk_is_flagged_as_quiet() -> None:
    cols = timeline(100, _with(100, f.SILENCE_RATIO, slice(20, 23), 0.97, 0.1))
    (flag,) = _of(_flags(cols), FlagKind.QUIET)
    assert (flag.first_chunk, flag.last_chunk) == (20, 22)
    assert flag.value == 0.97


def test_a_true_peak_at_full_scale_is_flagged_as_clipping() -> None:
    cols = timeline(100, _with(100, f.TRUE_PEAK, slice(55, 56), 0.4, -3.0))
    (flag,) = _of(_flags(cols), FlagKind.CLIPPING)
    assert flag.first_chunk == 55 and flag.value == 0.4


def test_a_run_without_cuts_is_flagged_as_a_long_take() -> None:
    cuts = np.full(100, 3.0)
    cuts[10:15] = 0.0
    cols = timeline(100, {f.CUT_COUNT: cuts, f.GRADUAL_COUNT: 0.0})
    (flag,) = _of(_flags(cols), FlagKind.LONG_TAKE)
    assert (flag.first_chunk, flag.last_chunk) == (10, 14)
    assert (flag.start_s, flag.end_s) == (600.0, 900.0)
    assert flag.value == 5.0  # chunks


def test_a_run_shorter_than_the_minimum_is_not_a_long_take() -> None:
    cuts = np.full(100, 3.0)
    cuts[10 : 10 + FLAG_NO_CUT_CHUNKS - 1] = 0.0
    cols = timeline(100, {f.CUT_COUNT: cuts, f.GRADUAL_COUNT: 0.0})
    assert _of(_flags(cols), FlagKind.LONG_TAKE) == []


def test_a_gradual_transition_ends_a_run_without_cuts() -> None:
    cuts = np.zeros(100)
    gradual = np.zeros(100)
    gradual[12] = 1.0
    cols = timeline(100, {f.CUT_COUNT: cuts, f.GRADUAL_COUNT: gradual})
    runs = [(x.first_chunk, x.last_chunk) for x in _of(_flags(cols), FlagKind.LONG_TAKE)]
    assert runs == [(0, 11), (13, 99)]


def test_flags_come_in_time_order() -> None:
    values = _with(100, f.CUT_COUNT, slice(80, 81), 25.0, 2.0)
    values |= _with(100, f.SILENCE_RATIO, slice(10, 11), 0.99, 0.1)
    values |= _with(100, f.TRUE_PEAK, slice(50, 51), 1.0, -3.0)
    flags = _flags(timeline(100, values))
    assert [x.start_s for x in flags] == sorted(x.start_s for x in flags)
    assert len(flags) == 3


def test_a_film_without_audio_gets_the_video_flags_only() -> None:
    cols = timeline(100, _with(100, f.CUT_COUNT, slice(40, 42), 20.0, 2.0), audio=False)
    flags = _flags(cols)
    assert {x.kind for x in flags} == {FlagKind.FAST_CUTTING}


def test_a_missing_loudness_is_never_flagged_as_loud_or_quiet() -> None:
    lufs = np.full(100, -25.0)
    lufs[10:20] = -70.0
    assert _flags(timeline(100, {f.LUFS: lufs})) == []


def test_an_empty_film_has_no_flags() -> None:
    assert _flags(timeline(0)) == []


def test_the_same_input_gives_identical_output() -> None:
    cols = timeline(100, _with(100, f.CUT_COUNT, slice(40, 42), 20.0, 2.0))
    assert _flags(cols) == _flags(cols)
