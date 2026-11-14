"""Synthetic timelines for the analysis tests: pure arrays in the store's column format, with
change points, peaks and flat stretches known by construction. No ffmpeg, no files."""

from collections.abc import Mapping

import numpy as np
import numpy.typing as npt

from filmanalyser.core import features as f

Columns = dict[str, npt.NDArray[np.generic]]
CHUNK_S = 60.0
AUDIO = (f.LUFS, f.SPEECH_RATIO, f.TONAL_RATIO, f.SILENCE_RATIO)
VIDEO = (f.BRIGHTNESS, f.CONTRAST, f.COLOURFULNESS, f.WARMTH)


def timeline(
    count: int,
    values: Mapping[str, npt.NDArray[np.float64] | float] | None = None,
    *,
    audio: bool = True,
    last_s: float = CHUNK_S,
) -> Columns:
    """A film of `count` chunks. Every feature is constant unless `values` gives a series (or a
    constant) for it. `audio=False` leaves the audio columns out, as for a film without sound."""
    names = [f.CUT_COUNT, f.GRADUAL_COUNT, f.TRUE_PEAK, *VIDEO, *(AUDIO if audio else ())]
    base = {name: np.full(count, 1.0) for name in names}
    base[f.LUFS] = np.full(count, -25.0)
    base[f.TRUE_PEAK] = np.full(count, -3.0)
    base[f.SPEECH_RATIO] = np.full(count, 0.5)
    base[f.TONAL_RATIO] = np.full(count, 0.3)
    base[f.SILENCE_RATIO] = np.full(count, 0.1)
    for name, series in (values or {}).items():
        base[name] = np.broadcast_to(np.asarray(series, dtype=np.float64), (count,)).copy()
    starts = np.arange(count) * CHUNK_S
    ends = starts + CHUNK_S
    if count:
        ends[-1] = starts[-1] + last_s
    columns: Columns = {
        f.CHUNK_INDEX: np.arange(count, dtype=np.int32),
        f.START_S: starts,
        f.END_S: ends,
    }
    columns.update({name: base[name] for name in names if name in base})
    return columns


def blocks(sizes: list[int], levels: list[float]) -> npt.NDArray[np.float64]:
    """A series made of constant blocks: `sizes[i]` chunks at `levels[i]`."""
    return np.concatenate([np.full(n, v) for n, v in zip(sizes, levels, strict=True)])


def block_film(sizes: list[int], levels: list[float], *, audio: bool = True) -> Columns:
    """A film whose every state feature steps together between constant blocks."""
    n = sum(sizes)
    series = blocks(sizes, levels)
    values: dict[str, npt.NDArray[np.float64] | float] = {
        f.CUT_COUNT: series * 4.0,
        f.BRIGHTNESS: series * 0.1,
        f.CONTRAST: series * 0.05,
        f.COLOURFULNESS: series * 0.08,
        f.WARMTH: series * 0.02,
    }
    if audio:
        values |= {
            f.LUFS: -40.0 + series * 5.0,
            f.SPEECH_RATIO: series * 0.1,
            f.TONAL_RATIO: series * 0.1,
            f.SILENCE_RATIO: 1.0 - series * 0.1,
        }
    return timeline(n, values, audio=audio)


def noise_film(count: int, seed: int = 7, *, audio: bool = True) -> Columns:
    """Independent noise on every state feature: structure-free by construction."""
    rng = np.random.default_rng(seed)
    names = [f.CUT_COUNT, *VIDEO, *(AUDIO if audio else ())]
    values: dict[str, npt.NDArray[np.float64] | float] = {
        name: rng.normal(1.0, 0.3, count) for name in names
    }
    if audio:
        values[f.LUFS] = rng.normal(-25.0, 3.0, count)
    return timeline(count, values, audio=audio)


def golden_film() -> Columns:
    """A tent-shaped film (25 / 50 / 25 chunks) with a burst of fast cutting, a silent chunk, a
    clipping chunk and a flat stretch of pacing, so every analysis has something to report."""
    cols = block_film([25, 50, 25], [1.0, 3.0, 1.0])
    cuts = np.where(np.arange(100) % 2 == 0, 6.0, 14.0) + 6.0 * (blocks([25, 50, 25], [0, 1, 0]))
    cuts[40:48] = 10.0  # a flat stretch of pacing
    cuts[60:62] = 90.0  # a burst of fast cutting
    cuts[85:90] = 0.0  # a long take (no cuts, no transitions)
    cols[f.CUT_COUNT] = cuts
    cols[f.GRADUAL_COUNT] = np.where(np.arange(100) % 7 == 0, 1.0, 0.0)
    cols[f.GRADUAL_COUNT][85:90] = 0.0
    cols[f.SILENCE_RATIO] = np.where(np.arange(100) == 10, 0.97, 0.3)  # one silent chunk
    cols[f.LUFS] = np.where((np.arange(100) // 2) == 30, -10.0, cols[f.LUFS])  # loud with the burst
    cols[f.TRUE_PEAK] = np.where(np.arange(100) == 55, 0.3, -3.0)
    return cols
