"""Block convolution equals the whole-signal convolution, and loudness on a 5.1 minute keeps its
working memory bounded (the 2.2 GB peak on a real 5.1 film, DECISIONS #99)."""

import tracemalloc

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from filmanalyser.extractors._convolve import fft_convolve
from filmanalyser.extractors._kweighting import _kernel, k_weight
from filmanalyser.extractors._truepeak import true_peak_linear
from filmanalyser.extractors.loudness import block_energies, channel_weights

MiB = 1 << 20


@settings(max_examples=60, deadline=None)
@given(
    count=st.integers(1, 400),
    taps=st.integers(1, 70),
    block=st.integers(1, 130),
    seed=st.integers(0, 1000),
)
def test_blocks_give_the_whole_convolution(count: int, taps: int, block: int, seed: int) -> None:
    rng = np.random.default_rng(seed)
    signal, kernel = rng.standard_normal(count), rng.standard_normal(taps)
    np.testing.assert_allclose(
        fft_convolve(signal, kernel, block), np.convolve(signal, kernel), atol=1e-9
    )


def test_a_float32_signal_is_accepted() -> None:
    signal = np.linspace(-1, 1, 300, dtype=np.float32)
    kernel = np.array([0.5, 0.25])
    np.testing.assert_allclose(
        fft_convolve(signal, kernel, 64), np.convolve(signal.astype(np.float64), kernel), atol=1e-6
    )


def test_k_weight_does_not_depend_on_the_block_size() -> None:
    rng = np.random.default_rng(3)
    samples = rng.standard_normal((20000, 2)).astype(np.float32)
    whole = np.stack(
        [np.convolve(samples[:, c], _kernel(48000), "full")[:20000] for c in (0, 1)], 1
    )
    np.testing.assert_allclose(k_weight(samples, 48000), whole, atol=1e-9)


def test_channel_by_channel_energy_equals_the_weighted_sum_over_channels() -> None:
    rng = np.random.default_rng(4)
    core = rng.standard_normal((9000, 6))
    weights = channel_weights(6)
    block, hop = 3000, 750
    starts = np.arange(0, len(core) - block + 1, hop)
    direct = [float(np.sum(weights * np.mean(core[s : s + block] ** 2, axis=0))) for s in starts]
    np.testing.assert_allclose(block_energies(core, block, hop, weights), direct, rtol=1e-9)


def test_five_one_loudness_work_stays_under_a_bound() -> None:
    """A real 62 s 5.1 window: K-weighting, block energies and true peak together. Before the fix
    this peaked at about 800 MiB of Python-allocated memory; it is 400 MiB now."""
    rng = np.random.default_rng(5)
    window = (rng.standard_normal((62 * 48000, 6)) * 0.1).astype(np.float32)
    tracemalloc.start()
    try:
        weighted = k_weight(window, 48000)
        block_energies(weighted, 19200, 4800, channel_weights(6))
        true_peak_linear(window, 3 * 48000)
        peak = tracemalloc.get_traced_memory()[1]
    finally:
        tracemalloc.stop()
    assert peak < 600 * MiB, f"{peak / MiB:.0f} MiB"


@pytest.mark.parametrize("channels", [1, 2])
def test_mono_and_stereo_energies_are_unchanged(channels: int) -> None:
    core = np.ones((4800, channels))
    energy = block_energies(core, 4800, 1200, channel_weights(channels))
    np.testing.assert_allclose(energy, [float(channels)])
