"""Loudness: integrated loudness (ITU-R BS.1770-4, gated), channel-weighted, plus sample and true
peak, per chunk core (DECISIONS #61, #68). Pure: it reads the chunk's audio and returns numbers.

Integrated loudness: the window (overlap included, so the filter has warmed up) is K-weighted; the
core's 400 ms blocks (100 ms hop) are gated twice: an absolute gate at -70 LUFS, then a relative
gate 10 LU under the mean of what passed. Channels are weighted as the standard says: front
channels and the centre 1.0, the LFE channel not at all, surround channels 1.41 (5.1 order
L R C LFE Ls Rs). Other layouts weight every channel 1.0. A chunk with no block above the absolute
gate reads the -70 LUFS floor, which is also the reading of digital silence.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from functools import cache

import numpy as np
import numpy.typing as npt

from filmanalyser.core.chunk import Chunk
from filmanalyser.core.config import (
    LOUDNESS_ABS_GATE_LUFS,
    LOUDNESS_BLOCK_S,
    LOUDNESS_HOP_S,
    LOUDNESS_OFFSET_LU,
    LOUDNESS_REL_GATE_LU,
    PEAK_FLOOR_DBFS,
)
from filmanalyser.core.errors import InputError
from filmanalyser.extractors._kweighting import k_weight
from filmanalyser.extractors._truepeak import true_peak_linear

NAME = "loudness"
VERSION = 2
FEATURES = ("integrated_lufs", "peak_dbfs", "true_peak_dbfs")
SURROUND_WEIGHT = 1.41  # BS.1770-4: the surround channels of a 5.1 mix
_TINY = 1e-30  # keeps log10 finite for a silent block (it then fails the absolute gate)


@cache
def channel_weights(channels: int) -> npt.NDArray[np.float64]:
    """BS.1770 channel weights for a layout: 5.1 in L R C LFE Ls Rs order gets the surround and LFE
    weights; any other count weights every channel 1.0."""
    if channels == 6:
        return np.array([1.0, 1.0, 1.0, 0.0, SURROUND_WEIGHT, SURROUND_WEIGHT])
    return np.ones(channels)


def block_energies(
    core: npt.NDArray[np.float64], block: int, hop: int, weights: npt.NDArray[np.float64]
) -> npt.NDArray[np.float64]:
    """Weighted mean square of each block, summed over channels. A core shorter than one block is
    one block; an empty core gives one zero block."""
    count = len(core)
    if count == 0:
        return np.zeros(1)
    if count < block:
        return np.array([float(np.sum(weights * np.mean(core * core, axis=0)))])
    starts = np.arange(0, count - block + 1, hop)
    csum = np.vstack([np.zeros((1, core.shape[1])), np.cumsum(core * core, axis=0)])
    sums = csum[starts + block] - csum[starts]
    return np.asarray(np.sum(sums * weights, axis=1) / block, dtype=np.float64)


def _loudness(energy: npt.NDArray[np.float64]) -> npt.NDArray[np.float64]:
    return LOUDNESS_OFFSET_LU + 10 * np.log10(np.maximum(energy, _TINY))


def integrated_lufs(weighted: npt.NDArray[np.float64], core_offset: int, rate: int) -> float:
    """Gated integrated loudness of the core of a K-weighted window (`core_offset` samples in)."""
    block = max(1, round(LOUDNESS_BLOCK_S * rate))
    hop = max(1, round(LOUDNESS_HOP_S * rate))
    weights = channel_weights(weighted.shape[1])
    energy = block_energies(weighted[core_offset:], block, hop, weights)
    loud = _loudness(energy)
    passed = loud > LOUDNESS_ABS_GATE_LUFS
    if not passed.any():
        return LOUDNESS_ABS_GATE_LUFS
    relative = float(_loudness(np.array([energy[passed].mean()]))[0]) + LOUDNESS_REL_GATE_LU
    kept = passed & (loud > relative)
    return float(_loudness(np.array([energy[kept].mean()]))[0])


def peak_dbfs(core: npt.NDArray[np.float32]) -> float:
    """Sample peak of the core, in dBFS (the raw samples, not K-weighted)."""
    peak = float(np.max(np.abs(core))) if core.size else 0.0
    if peak <= 0.0:
        return PEAK_FLOOR_DBFS
    return max(PEAK_FLOOR_DBFS, 20 * float(np.log10(peak)))


def true_peak_dbfs(window: npt.NDArray[np.float32], core_offset: int, rate: int) -> float:
    """True peak of the core, in dBFS: the largest value between samples (4x oversampled). `rate`
    is accepted for the signature of the other audio measures; the oversampling is by a fixed
    factor, so the result does not depend on it."""
    del rate
    peak = true_peak_linear(np.asarray(window, dtype=np.float64), core_offset)
    if peak <= 0.0:
        return PEAK_FLOOR_DBFS
    return max(PEAK_FLOOR_DBFS, 20 * float(np.log10(peak)))


@dataclass(frozen=True)
class Loudness:
    name: str = NAME
    version: int = VERSION
    features: tuple[str, ...] = FEATURES
    needs_audio: bool = True

    def extract(self, chunk: Chunk) -> Mapping[str, float]:
        audio = chunk.audio
        if audio is None:
            raise InputError(key="error.input.bad_setting", name="audio")
        weighted = k_weight(audio.samples, audio.rate)
        offset = chunk.audio_core_offset
        return {
            "integrated_lufs": integrated_lufs(weighted, offset, audio.rate),
            "peak_dbfs": peak_dbfs(chunk.core_audio),
            "true_peak_dbfs": true_peak_dbfs(audio.samples, offset, audio.rate),
        }


EXTRACTOR = Loudness()
