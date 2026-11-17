"""Chart geometry: values in, coordinates inside the plot area out (inline SVG, no script).

Pure numbers. The template draws the lines, markers and bands this module places; it never
decides where anything goes. Every coordinate is rounded to one decimal so the same film always
gives the same bytes.
"""

from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

from filmanalyser.report.display import SECONDS_PER_MINUTE, number_text
from filmanalyser.report.resources.keys import MARK_BAND

Values = npt.NDArray[np.float64]

WIDTH = 640.0
HEIGHT = 262.0
LEFT = 48.0  # room for the value labels
RIGHT = WIDTH - 8.0
TOP = 12.0
BOTTOM = HEIGHT - 48.0  # room for the time labels and the axis title below them
TICK_OFFSET = 16.0  # the time labels sit this far under the axis
AXIS_TITLE_Y = HEIGHT - 8.0  # the axis title's baseline
_STEPS_MINUTES = (1, 2, 5, 10, 15, 30, 60, 120, 240)
_MAX_TICKS = 8
_FLAT_SPAN = 1.0  # a series that does not vary is drawn in a range this wide
_Y_TICKS = 3


@dataclass(frozen=True)
class Series:
    label_key: str
    style: str  # a CSS class (s1 .. s4): colour and dash pattern
    values: Values  # one per chunk; NaN where nothing was measured


@dataclass(frozen=True)
class Marker:
    seconds: float
    kind: str  # "break" or "peak": a CSS class
    label_key: str
    text: str  # the time, as the reader sees it


@dataclass(frozen=True)
class Span:
    start_s: float
    end_s: float
    label_key: str  # names what the shaded stretch is, in the chart's legend


@dataclass(frozen=True)
class Frame:
    """The film clock a chart is drawn on: where each value lies, and where the film ends."""

    middles: Values  # the middle of each chunk, in seconds
    film_s: float


@dataclass(frozen=True)
class Notes:
    """What is drawn over the lines: vertical markers, and shaded stretches."""

    markers: tuple[Marker, ...] = ()
    bands: tuple[Span, ...] = ()
    stacked: bool = False  # draw the series as bands stacked from the bottom, not as lines


@dataclass(frozen=True)
class Line:
    label_key: str
    style: str
    segments: tuple[str, ...]  # SVG "x,y x,y" lists; a gap in the data starts a new one


@dataclass(frozen=True)
class Area:
    label_key: str
    style: str  # a CSS class (a1 .. a3): a fill from the colour tokens
    points: str  # SVG polygon: along the band's top edge, then back along its bottom edge


@dataclass(frozen=True)
class PlacedMarker:
    x: float
    kind: str
    label_key: str
    text: str


@dataclass(frozen=True)
class PlacedBand:
    x: float
    width: float


@dataclass(frozen=True)
class Tick:
    pos: float
    text: str


@dataclass(frozen=True)
class LegendEntry:
    label_key: str
    kind: str  # the CSS class of its swatch


@dataclass(frozen=True)
class Chart:
    key: str  # strings.toml prefix: <key>.label, <key>.caption
    lines: tuple[Line, ...]
    markers: tuple[PlacedMarker, ...]
    bands: tuple[PlacedBand, ...]
    x_ticks: tuple[Tick, ...]
    y_ticks: tuple[Tick, ...]
    legend: tuple[LegendEntry, ...]  # what the markers and bands mean, each once, in order
    areas: tuple[Area, ...] = ()  # stacked bands (shares that add up), instead of lines
    tick_offset: float = TICK_OFFSET
    axis_title_y: float = AXIS_TITLE_Y
    width: float = WIDTH
    height: float = HEIGHT
    left: float = LEFT
    right: float = RIGHT
    top: float = TOP
    bottom: float = BOTTOM


def nice_step(film_minutes: float) -> int:
    """The smallest tick spacing, in minutes, that keeps the time axis to a few labels."""
    return next((s for s in _STEPS_MINUTES if film_minutes / s <= _MAX_TICKS), _STEPS_MINUTES[-1])


def _x(seconds: float, film_s: float) -> float:
    share = min(max(seconds / film_s, 0.0), 1.0) if film_s > 0 else 0.0
    return round(LEFT + share * (RIGHT - LEFT), 1)


def _y(value: float, low: float, high: float) -> float:
    share = min(max((value - low) / (high - low), 0.0), 1.0)
    return round(BOTTOM - share * (BOTTOM - TOP), 1)


def _range(lines: tuple[Series, ...], fixed: tuple[float, float] | None) -> tuple[float, float]:
    if fixed is not None:
        return fixed
    measured = np.concatenate([s.values[np.isfinite(s.values)] for s in lines])
    if measured.size == 0:
        return 0.0, _FLAT_SPAN
    low, high = float(measured.min()), float(measured.max())
    if high - low < 1e-9:
        return low - _FLAT_SPAN / 2, high + _FLAT_SPAN / 2
    return low, high


def _segments(frame: Frame, values: Values, low: float, high: float) -> tuple[str, ...]:
    runs: list[list[str]] = []
    previous_missing = True
    for t, v in zip(frame.middles, values, strict=True):
        if not np.isfinite(v):
            previous_missing = True
            continue
        if previous_missing:
            runs.append([])
        runs[-1].append(f"{_x(float(t), frame.film_s)},{_y(float(v), low, high)}")
        previous_missing = False
    # a lone point is drawn as a zero-length line, which a round cap shows as a dot
    return tuple(" ".join(r if len(r) > 1 else r * 2) for r in runs)


def _areas(frame: Frame, lines: tuple[Series, ...], low: float, high: float) -> tuple[Area, ...]:
    """Bands stacked from the bottom in series order; a missing value counts as nothing."""
    xs = [_x(float(t), frame.film_s) for t in frame.middles]
    floor = np.zeros(len(xs))
    out = []
    for s in lines:
        ceiling = floor + np.where(np.isfinite(s.values), s.values, 0.0)
        top = [f"{x},{_y(float(v), low, high)}" for x, v in zip(xs, ceiling, strict=True)]
        base = [f"{x},{_y(float(v), low, high)}" for x, v in zip(xs, floor, strict=True)]
        out.append(Area(s.label_key, s.style, " ".join([*top, *reversed(base)])))
        floor = ceiling
    return tuple(out)


def _time_ticks(film_s: float) -> tuple[Tick, ...]:
    minutes = film_s / SECONDS_PER_MINUTE
    step = nice_step(minutes)
    return tuple(
        Tick(_x(m * SECONDS_PER_MINUTE, film_s), str(m)) for m in range(0, int(minutes) + 1, step)
    )


def _value_ticks(low: float, high: float) -> tuple[Tick, ...]:
    values = np.linspace(low, high, _Y_TICKS)
    return tuple(Tick(_y(float(v), low, high), number_text(float(v))) for v in values)


def build_chart(
    key: str,
    frame: Frame,
    lines: tuple[Series, ...],
    y_range: tuple[float, float] | None = None,
    notes: Notes | None = None,
) -> Chart:
    low, high = _range(lines, y_range)
    film_s, notes = frame.film_s, notes or Notes()
    return Chart(
        key=key,
        lines=()
        if notes.stacked
        else tuple(
            Line(s.label_key, s.style, _segments(frame, s.values, low, high)) for s in lines
        ),
        areas=_areas(frame, lines, low, high) if notes.stacked else (),
        markers=tuple(
            PlacedMarker(_x(m.seconds, film_s), m.kind, m.label_key, m.text) for m in notes.markers
        ),
        bands=tuple(_band(b, film_s) for b in notes.bands),
        x_ticks=_time_ticks(film_s),
        y_ticks=_value_ticks(low, high),
        legend=_legend(notes),
    )


def _legend(notes: Notes) -> tuple[LegendEntry, ...]:
    entries = [LegendEntry(m.label_key, m.kind) for m in notes.markers]
    entries += [LegendEntry(b.label_key, MARK_BAND) for b in notes.bands]
    return tuple({e.label_key: e for e in entries}.values())


def _band(span: Span, film_s: float) -> PlacedBand:
    left = _x(span.start_s, film_s)
    return PlacedBand(left, round(_x(span.end_s, film_s) - left, 1))
