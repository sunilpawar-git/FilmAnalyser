"""Flags: timestamped moments that deserve a look, each raised by one stated rule (DECISIONS #91).
Consecutive chunks that raise the same rule are one flag. Pure."""

from dataclasses import dataclass
from enum import StrEnum

import numpy as np
import numpy.typing as npt

from filmanalyser.analysis.timeline import Series, Timeline, zscores
from filmanalyser.core import features as f
from filmanalyser.core.config import (
    FLAG_NO_CUT_CHUNKS,
    FLAG_OUTLIER_Z,
    FLAG_SILENCE_RATIO,
    FLAG_TRUE_PEAK_DBFS,
)


class FlagKind(StrEnum):
    FAST_CUTTING = "fast_cutting"  # cut rate far above the film's usual
    LOUD = "loud"  # loudness far above the film's usual
    QUIET = "quiet"  # nearly every window of the chunk is silence
    CLIPPING = "clipping"  # true peak at or above full scale
    LONG_TAKE = "long_take"  # several chunks in a row without a cut or transition


@dataclass(frozen=True)
class Flag:
    kind: FlagKind
    first_chunk: int
    last_chunk: int  # inclusive
    start_s: float
    end_s: float
    value: float  # the largest z (fast cutting, loud), silence share, true peak, or chunks (take)


def _runs(mask: npt.NDArray[np.bool_]) -> list[tuple[int, int]]:
    """(first, last) of every run of True, in order."""
    padded = np.concatenate([[False], mask, [False]]).astype(np.int8)
    edges = np.flatnonzero(np.diff(padded))
    return [(int(a), int(b) - 1) for a, b in zip(edges[::2], edges[1::2], strict=True)]


def _flags(
    timeline: Timeline,
    kind: FlagKind,
    mask: npt.NDArray[np.bool_],
    values: Series,
    min_run: int = 1,
) -> list[Flag]:
    return [
        Flag(
            kind,
            first,
            last,
            float(timeline.start_s[first]),
            float(timeline.end_s[last]),
            float(last - first + 1)
            if kind is FlagKind.LONG_TAKE
            else float(np.nanmax(values[first : last + 1])),
        )
        for first, last in _runs(mask)
        if last - first + 1 >= min_run
    ]


def _above(values: Series, limit: float) -> npt.NDArray[np.bool_]:
    with np.errstate(invalid="ignore"):  # a missing value compares false
        return np.asarray(values >= limit)


# (kind, series, judged in standard deviations?, limit): a chunk at or above the limit is flagged.
_RULES = (
    (FlagKind.FAST_CUTTING, f.CUT_RATE, True, FLAG_OUTLIER_Z),
    (FlagKind.LOUD, f.LUFS, True, FLAG_OUTLIER_Z),
    (FlagKind.QUIET, f.SILENCE_RATIO, False, FLAG_SILENCE_RATIO),
    (FlagKind.CLIPPING, f.TRUE_PEAK, False, FLAG_TRUE_PEAK_DBFS),
)


def find_flags(timeline: Timeline) -> tuple[Flag, ...]:
    """Every flag in the film, in time order. A rule whose feature the film lacks (a film without
    audio has no loudness, silence or peak) raises nothing."""
    found: list[Flag] = []
    for kind, name, in_sigma, limit in _RULES:
        if name in timeline.series:
            values = zscores(timeline.series[name]) if in_sigma else timeline.series[name]
            found += _flags(timeline, kind, _above(values, limit), values)
    rate = timeline.series[f.CUT_RATE]
    found += _flags(timeline, FlagKind.LONG_TAKE, rate == 0.0, rate, FLAG_NO_CUT_CHUNKS)
    return tuple(sorted(found, key=lambda x: (x.start_s, x.kind)))
