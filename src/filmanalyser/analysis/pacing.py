"""Pacing: how fast the film is cut, and where it holds one speed (DECISIONS #91). Pure."""

from dataclasses import dataclass

import numpy as np

from filmanalyser.analysis.timeline import Series, Timeline, zscores
from filmanalyser.core import features as f
from filmanalyser.core.config import PACING_PLATEAU_MIN_CHUNKS, PACING_PLATEAU_RANGE_Z


@dataclass(frozen=True)
class Plateau:
    """A stretch whose cut rate stays within a narrow band while the film around it varies."""

    first_chunk: int
    last_chunk: int  # inclusive
    start_s: float
    end_s: float
    mean_rate: float  # cuts and gradual transitions per minute


@dataclass(frozen=True)
class Pacing:
    rate_per_min: tuple[float, ...]
    mean_rate: float
    plateaus: tuple[Plateau, ...]


def _run_end(z: Series, first: int) -> int:
    """Last chunk of the run that starts at `first` and keeps its z range within the band."""
    low = high = z[first]
    last = first
    for i in range(first + 1, len(z)):
        low, high = min(low, z[i]), max(high, z[i])
        if high - low > PACING_PLATEAU_RANGE_Z:
            break
        last = i
    return last


def _plateaus(timeline: Timeline, rate: Series) -> tuple[Plateau, ...]:
    z = np.nan_to_num(zscores(rate), nan=np.inf)  # a chunk without a rate is never part of a run
    found: list[Plateau] = []
    first = 0
    while first < len(z):
        last = _run_end(z, first) if np.isfinite(z[first]) else first
        if last - first + 1 >= PACING_PLATEAU_MIN_CHUNKS:
            found.append(_plateau(timeline, rate, first, last))
            first = last + 1
        else:
            first += 1
    return tuple(found)


def _plateau(timeline: Timeline, rate: Series, first: int, last: int) -> Plateau:
    return Plateau(
        first_chunk=first,
        last_chunk=last,
        start_s=float(timeline.start_s[first]),
        end_s=float(timeline.end_s[last]),
        mean_rate=float(np.mean(rate[first : last + 1])),
    )


def analyse_pacing(timeline: Timeline) -> Pacing:
    rate = timeline.series[f.CUT_RATE]
    measured = rate[np.isfinite(rate)]
    return Pacing(
        rate_per_min=tuple(float(x) for x in rate),
        mean_rate=float(measured.mean()) if len(measured) else 0.0,
        plateaus=_plateaus(timeline, rate),
    )
