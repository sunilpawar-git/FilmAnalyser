"""The film's timeline: the store's columns as aligned series, plus the two shared operations on
them (z-score, smooth). Pure functions over arrays, no I/O (DECISIONS #90).

A series holds one value per chunk. A value that was never measured is NaN, never a number: the
loudness floor (digital silence reads exactly -70 LUFS) is a missing loudness, not a very quiet one.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

import numpy as np
import numpy.typing as npt

from filmanalyser.core import features as f
from filmanalyser.core.config import (
    LOUDNESS_ABS_GATE_LUFS,
    SECONDS_PER_MINUTE,
    TIMELINE_MIN_TAIL_FRACTION,
    Z_EPSILON,
)
from filmanalyser.core.errors import AnalysisError

Series = npt.NDArray[np.float64]
Columns = Mapping[str, npt.NDArray[np.generic]]
_REQUIRED = (f.START_S, f.END_S, f.CUT_COUNT, f.GRADUAL_COUNT)


@dataclass(frozen=True)
class Timeline:
    """Per-chunk series on the container clock. `series` holds the cut rate and every state or
    flag column the film has; `film_end_s` is where the film really ends (a dropped tail chunk
    does not move it)."""

    start_s: Series
    end_s: Series
    film_end_s: float
    series: Mapping[str, Series]

    @property
    def count(self) -> int:
        return len(self.start_s)

    @property
    def state_names(self) -> tuple[str, ...]:
        return tuple(name for name in f.STATE_FEATURES if name in self.series)

    @property
    def audio_used(self) -> bool:
        return any(name in self.series for name in f.AUDIO_STATE_COLUMNS)


def _bad(name: str) -> AnalysisError:
    return AnalysisError(key="error.analysis.bad_timeline", name=name)


def _floats(columns: Columns, name: str, count: int | None) -> Series:
    if name not in columns:
        raise _bad(name)
    values = np.asarray(columns[name], dtype=np.float64)
    if values.ndim != 1 or (count is not None and len(values) != count):
        raise _bad(name)
    return values


def _clean(values: Series) -> Series:
    return np.where(np.isfinite(values), values, np.nan)


def _read_only(values: Series) -> Series:
    values = np.array(values, dtype=np.float64)
    values.setflags(write=False)
    return values


def _kept(start_s: Series, end_s: Series) -> int:
    """Chunks that count: a last chunk much shorter than the others is too short to measure."""
    count = len(start_s)
    if count < 2:
        return count
    lengths = end_s - start_s
    short = lengths[-1] < TIMELINE_MIN_TAIL_FRACTION * float(np.median(lengths))
    return count - 1 if short else count


def build_timeline(columns: Columns) -> Timeline:
    """Read the store's columns (`FeatureStore.read_columns()`) into a `Timeline`.
    Raises `AnalysisError` when a required column is missing or the columns do not line up."""
    start = _floats(columns, f.START_S, None)
    count = len(start)
    end = _floats(columns, f.END_S, count)
    if count and not (
        np.all(np.isfinite(start)) and np.all(np.isfinite(end)) and np.all(end > start)
    ):
        raise _bad(f.END_S)
    cuts, gradual = (_floats(columns, name, count) for name in (f.CUT_COUNT, f.GRADUAL_COUNT))
    keep = _kept(start, end)
    minutes = (end - start) / SECONDS_PER_MINUTE
    wanted = (*f.STATE_FEATURES[1:], f.TRUE_PEAK)
    series = {f.CUT_RATE: _clean((cuts + gradual) / np.where(minutes > 0, minutes, np.nan))}
    series.update({n: _clean(_floats(columns, n, count)) for n in wanted if n in columns})
    if f.LUFS in series:
        series[f.LUFS] = np.where(series[f.LUFS] <= LOUDNESS_ABS_GATE_LUFS, np.nan, series[f.LUFS])
    return Timeline(
        start_s=_read_only(start[:keep]),
        end_s=_read_only(end[:keep]),
        film_end_s=float(end[-1]) if count else 0.0,
        series=MappingProxyType({n: _read_only(v[:keep]) for n, v in series.items()}),
    )


def zscores(values: Series) -> Series:
    """Standard scores over the film, from the measured values only. A series that does not vary
    scores zero everywhere it was measured; a missing value stays missing."""
    measured = values[np.isfinite(values)]
    out = np.full(len(values), np.nan)
    if len(measured) == 0:
        return out
    spread = float(measured.std())
    shift = values - float(measured.mean())
    out[np.isfinite(values)] = shift[np.isfinite(values)] / spread if spread > Z_EPSILON else 0.0
    return out


def smooth(values: Series, width: int) -> Series:
    """Centred moving average over `width` chunks (truncated at the ends), skipping missing values;
    a window with nothing measured stays missing."""
    half = width // 2
    out = np.full(len(values), np.nan)
    for i in range(len(values)):
        window = values[max(0, i - half) : i + half + 1]
        measured = window[np.isfinite(window)]
        if len(measured):
            out[i] = float(measured.mean())
    return out


def film_state(
    timeline: Timeline, smooth_chunks: int
) -> tuple[tuple[str, ...], npt.NDArray[np.float64]]:
    """The film state: one smoothed z-scored column per state feature, in `state_names` order."""
    names = timeline.state_names
    columns = [smooth(zscores(timeline.series[n]), smooth_chunks) for n in names]
    return names, np.column_stack(columns)
