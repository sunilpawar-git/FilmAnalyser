"""Hard cuts and gradual transitions from frame-distance sequences (pure: no frames are read).

Ground truth is built into each sequence: a cut is one spike; a dissolve is a plateau of moderate
distances; a fade to black is a plateau with the black frame as a spike inside it (DECISIONS #79).
"""

import numpy as np

from filmanalyser.extractors.shot_cuts import _spike_blocks, _stretches, blend_residual, segment


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


# ---- the blend test (DECISIONS #84) ----------------------------------------------------------


def _frames_between(first: np.ndarray, last: np.ndarray, middles: list[np.ndarray]) -> np.ndarray:
    return np.stack([first, *middles, last]).astype(np.uint8)


def _scene(seed: int) -> np.ndarray:
    return np.random.default_rng(seed).integers(0, 256, size=(18, 32, 3)).astype(np.float64)


def test_a_dissolve_is_a_perfect_blend_of_its_ends() -> None:
    a, b = _scene(1), _scene(2)
    middles = [(1 - w) * a + w * b for w in (0.25, 0.5, 0.75)]
    assert blend_residual(_frames_between(a, b, middles), 0, 4) < 0.05


def test_a_fade_to_black_is_a_blend_with_black() -> None:
    a, black = _scene(3), np.zeros((18, 32, 3))
    middles = [(1 - w) * a for w in (0.25, 0.5, 0.75)]
    assert blend_residual(_frames_between(a, black, middles), 0, 4) < 0.05


def test_an_unrelated_middle_frame_is_not_a_blend() -> None:
    a, b = _scene(4), _scene(5)
    middles = [_scene(6), _scene(7), _scene(8)]  # a flash, an effect, a different picture
    assert blend_residual(_frames_between(a, b, middles), 0, 4) > 0.5


def test_two_frames_with_nothing_between_have_no_residual() -> None:
    assert blend_residual(_frames_between(_scene(1), _scene(2), []), 0, 1) == 0.0


def test_with_frames_a_stretch_that_is_not_a_blend_is_not_a_transition() -> None:
    distances = np.asarray([0.0, *([0.1] * 8), 0.0])
    a, b = _scene(1), _scene(2)
    blend = [(1 - w) * a + w * b for w in np.linspace(0.1, 0.9, 8)]
    good = _frames_between(a, b, blend)
    noise = _frames_between(a, b, [_scene(10 + i) for i in range(8)])
    assert len(segment(distances, 0, good).gradual) == 1
    assert segment(distances, 0, noise).gradual == ()
