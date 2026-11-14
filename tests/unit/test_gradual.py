"""Hard cuts and gradual transitions from frame-distance sequences (pure: no frames are read).

Ground truth is built into each sequence: a cut is one spike; a dissolve is a plateau of moderate
distances; a fade to black is a plateau with the black frame as a spike inside it (DECISIONS #79).
"""

import numpy as np

from filmanalyser.extractors.shot_cuts import _spike_blocks, _stretches, segment


def _d(values: list[float]) -> np.ndarray:
    return np.asarray(values, dtype=np.float64)


def test_a_single_spike_is_a_cut_on_the_frame_after_it() -> None:
    out = segment(_d([0.0, 0.0, 0.8, 0.0, 0.0]), context_frames=0)
    assert out.cuts == (3,)
    assert out.gradual == ()


def test_a_plateau_of_moderate_distances_is_a_gradual_transition() -> None:
    out = segment(_d([0.0, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.0]), context_frames=0)
    assert out.cuts == ()
    assert out.gradual == (
        (2, 9),
    )  # the stretch's first distance is frame 1, the transition starts at frame 2


def test_a_fade_to_black_is_one_transition_with_no_cut_at_the_black_frame() -> None:
    plateau = [0.1] * 6 + [0.7, 0.4, 0.3, 0.3, 0.3]
    out = segment(_d([0.0, *plateau, 0.0]), context_frames=0)
    assert out.cuts == ()
    assert len(out.gradual) == 1


def test_a_short_plateau_below_the_minimum_is_not_a_transition() -> None:
    out = segment(_d([0.0, 0.1, 0.1, 0.0, 0.0]), context_frames=0)  # two frames, sum 0.2
    assert out.gradual == ()
    assert out.cuts == ()


def test_a_spike_into_a_plateau_that_does_not_stay_gradual_is_a_cut() -> None:
    # a cut, then a short fade-in that is too short to count: the spike stays a cut
    out = segment(_d([0.0, 0.9, 0.1, 0.1, 0.0, 0.0]), context_frames=0)
    assert out.cuts == (2,)
    assert out.gradual == ()


def test_adjacent_spikes_form_one_block_and_are_judged_together() -> None:
    plateau = [0.1] * 6 + [0.7, 0.5] + [0.2] * 4  # two adjacent spikes in a fade
    out = segment(_d([0.0, *plateau]), context_frames=0)
    assert out.cuts == ()
    assert len(out.gradual) == 1


def test_spikes_closer_than_the_merge_distance_are_one_cut_keeping_the_strongest() -> None:
    out = segment(_d([0.0, 0.5, 0.0, 0.9, 0.0, 0.0]), context_frames=0)
    assert out.cuts == (4,)  # spikes at distance indices 1 and 3 merge; the 0.9 is kept


def test_events_before_the_core_are_not_returned() -> None:
    out = segment(_d([0.0, 0.8, 0.0, 0.0, 0.0, 0.8, 0.0]), context_frames=3)
    assert out.cuts == (6,)  # the spike at index 1 (frame 2) lies in the context


def test_a_transition_starting_in_the_context_is_not_returned() -> None:
    plateau = [0.1] * 8
    out = segment(_d([0.0, *plateau, 0.0]), context_frames=4)
    assert out.gradual == ()


def test_spike_blocks_group_adjacent_indices() -> None:
    assert _spike_blocks([2, 3, 7, 9, 10]) == [(2, 3), (7, 7), (9, 10)]
    assert _spike_blocks([]) == []


def test_stretches_are_the_frames_between_blocks() -> None:
    assert _stretches(0, 10, [(3, 3), (7, 8)]) == [(0, 3), (4, 7), (9, 10)]
