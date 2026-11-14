"""Which signal the voice detector hears (DECISIONS #86): a 5.1 track's centre, else the mix."""

import numpy as np

from filmanalyser.core.config import FIVE_ONE_CENTRE, FIVE_ONE_CHANNELS
from filmanalyser.media.vad import dialogue_signal


def test_a_mono_track_is_heard_as_it_is() -> None:
    samples = np.array([[0.1], [0.2], [-0.3]], dtype=np.float32)
    assert dialogue_signal(samples).tolist() == samples[:, 0].tolist()


def test_a_stereo_track_is_heard_as_the_average_of_its_channels() -> None:
    samples = np.array([[0.2, 0.4], [-0.2, 0.0]], dtype=np.float32)
    assert np.allclose(dialogue_signal(samples), [0.3, -0.1])


def test_a_five_point_one_track_is_heard_on_its_centre_channel() -> None:
    samples = np.zeros((4, FIVE_ONE_CHANNELS), dtype=np.float32)
    samples[:, FIVE_ONE_CENTRE] = [0.1, 0.2, 0.3, 0.4]
    samples[:, 0] = 0.9  # loud music on the left must not reach the detector
    out = dialogue_signal(samples)
    assert out.dtype == np.float32
    assert np.allclose(out, [0.1, 0.2, 0.3, 0.4])
