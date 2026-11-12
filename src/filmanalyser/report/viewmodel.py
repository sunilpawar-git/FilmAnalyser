"""ViewModel: stored columns in, display-ready values out (EXECUTION_PLAN section 0, DECISIONS #28).

Pure: no I/O and no locale. It turns numbers into the numbers a view shows and into chart
coordinates; it never formats for a language and never reads a resource. The view (the template)
only loops over these values and looks up their labels.
"""

from collections.abc import Mapping
from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

from filmanalyser.core.features import CUT_COUNT, END_S, START_S

CHART_WIDTH = 640.0
CHART_HEIGHT = 240.0
_SECONDS_PER_MINUTE = 60.0


@dataclass(frozen=True)
class CutRatePoint:
    minute: float  # middle of the chunk, in film minutes
    per_minute: float  # hard cuts per minute within the chunk
    x: float  # chart coordinates, inside [0, CHART_WIDTH] x [0, CHART_HEIGHT]
    y: float


@dataclass(frozen=True)
class ReportView:
    film: str
    film_seconds: float
    film_minutes_text: str
    total_cuts: int
    average_shot_s: float
    average_shot_text: str
    cut_rate: tuple[CutRatePoint, ...]
    chart_points: str  # the SVG polyline "x,y x,y ..."
    chart_width: float = CHART_WIDTH
    chart_height: float = CHART_HEIGHT


def _cut_rate(
    starts: npt.NDArray[np.float64],
    ends: npt.NDArray[np.float64],
    cuts: npt.NDArray[np.float64],
    film_seconds: float,
) -> tuple[CutRatePoint, ...]:
    if cuts.size == 0 or film_seconds <= 0:
        return ()
    spans = np.maximum(ends - starts, 1e-9)
    per_minute = cuts / spans * _SECONDS_PER_MINUTE
    scale = max(float(np.max(per_minute)), 1.0)  # the tallest point touches the top, never above
    middles = (starts + ends) / 2.0
    xs = middles / film_seconds * CHART_WIDTH
    ys = CHART_HEIGHT - per_minute / scale * CHART_HEIGHT
    return tuple(
        CutRatePoint(float(m / _SECONDS_PER_MINUTE), float(r), float(x), float(y))
        for m, r, x, y in zip(middles, per_minute, xs, ys, strict=True)
    )


def build_view(columns: Mapping[str, npt.ArrayLike], film: str) -> ReportView:
    """The report's numbers from the store's columns (`FeatureStore.read_columns`)."""
    starts = np.asarray(columns[START_S], dtype=np.float64)
    ends = np.asarray(columns[END_S], dtype=np.float64)
    cuts = np.asarray(columns[CUT_COUNT], dtype=np.float64)
    film_seconds = float(np.max(ends) - np.min(starts)) if starts.size else 0.0
    total = int(cuts.sum())
    average = film_seconds / (total + 1) if film_seconds > 0 else 0.0
    points = _cut_rate(starts, ends, cuts, film_seconds)
    return ReportView(
        film=film,
        film_seconds=film_seconds,
        film_minutes_text=f"{film_seconds / _SECONDS_PER_MINUTE:.1f}",
        total_cuts=total,
        average_shot_s=average,
        average_shot_text=f"{average:.1f}",
        cut_rate=points,
        chart_points=" ".join(f"{p.x:.1f},{p.y:.1f}" for p in points),
    )
