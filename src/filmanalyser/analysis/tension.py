"""Tension: one series per film from how fast it is cut and how loud it is, and its peak
(DECISIONS #91). The series is a mean of z-scores, so it is relative to the film itself. Pure."""

from dataclasses import dataclass

import numpy as np

from filmanalyser.analysis.timeline import Series, Timeline, smooth, zscores
from filmanalyser.core import features as f
from filmanalyser.core.config import TENSION_MIN_PEAK_Z, TENSION_SMOOTH_CHUNKS

COMPONENTS = (f.CUT_RATE, f.LUFS)  # the features tension is made of; absent ones are left out


@dataclass(frozen=True)
class TensionPeak:
    chunk: int
    start_s: float
    end_s: float
    value: float  # the series' value there (standard deviations above the film's mean)


@dataclass(frozen=True)
class Tension:
    values: tuple[float, ...]  # one per chunk
    components: tuple[str, ...]  # which features it was made of (video only when no audio)
    peak: TensionPeak | None  # None when nothing rises TENSION_MIN_PEAK_Z above the film


def _series(timeline: Timeline, components: tuple[str, ...]) -> Series:
    """Mean over the components that were measured in each chunk; 0 where none was."""
    if not components or timeline.count == 0:
        return np.zeros(timeline.count)
    stack = np.vstack([zscores(timeline.series[name]) for name in components])
    measured = np.isfinite(stack)
    mean = np.where(measured, stack, 0.0).sum(axis=0) / np.maximum(measured.sum(axis=0), 1)
    return smooth(mean, TENSION_SMOOTH_CHUNKS)


def _peak(timeline: Timeline, values: Series) -> TensionPeak | None:
    if len(values) == 0:
        return None
    chunk = int(np.argmax(values))  # the first of equal maxima
    if values[chunk] < TENSION_MIN_PEAK_Z:
        return None
    return TensionPeak(
        chunk=chunk,
        start_s=float(timeline.start_s[chunk]),
        end_s=float(timeline.end_s[chunk]),
        value=float(values[chunk]),
    )


def analyse_tension(timeline: Timeline) -> Tension:
    components = tuple(name for name in COMPONENTS if name in timeline.series)
    values = _series(timeline, components)
    return Tension(
        values=tuple(float(v) for v in values),
        components=components,
        peak=_peak(timeline, values),
    )
