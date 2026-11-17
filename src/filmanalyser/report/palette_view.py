"""The colour palette for the report: a strip of dominant colours over the film and the film's own
most common colours (view model: pure, DECISIONS 106).

The colours here are measured from the picture, so they are data, not design tokens: they are
written as `#rrggbb` text at run time and drawn as the fill of an SVG rectangle (the one place a
colour does not come from colors.toml). Everything else about the strip, its frame and labels, uses
the tokens.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import numpy as np
import numpy.typing as npt

from filmanalyser.core.features import PALETTE_DARK, PALETTE_PARTS, PALETTE_SIZE, palette_column
from filmanalyser.report.display import number_text

MAX_COLUMNS = 120
WIDTH = 640.0
TOP = 4.0
HEIGHT = 56.0  # the strip's height
SWATCHES = 5
_BYTE = 255
_PERCENT = 100.0

Colour = tuple[int, int, int]
Columns = Mapping[str, npt.NDArray[Any]]  # the store's columns by name


@dataclass(frozen=True)
class Segment:
    fill: str
    y: float
    height: float


@dataclass(frozen=True)
class StripColumn:
    x: float
    width: float
    segments: tuple[Segment, ...]


@dataclass(frozen=True)
class Swatch:
    fill: str
    share_text: str  # the percentage of the film's picture this colour holds, on average


@dataclass(frozen=True)
class PaletteView:
    top: float
    height: float
    width: float
    columns: tuple[StripColumn, ...]
    swatches: tuple[Swatch, ...]
    dark_text: str  # the film's average share of near-black (%); "" when not stored


def _hex(colour: Colour) -> str:
    return f"#{colour[0]:02x}{colour[1]:02x}{colour[2]:02x}"


def _slots(columns: Columns) -> list[tuple[list[np.ndarray], np.ndarray]] | None:
    """Per palette slot: its red, green, blue columns and its share column; None if not stored."""
    names = [
        [palette_column(rank, part) for part in PALETTE_PARTS]
        for rank in range(1, PALETTE_SIZE + 1)
    ]
    if not all(name in columns for row in names for name in row):
        return None
    return [
        ([np.asarray(columns[n], dtype=np.float64) for n in row[:3]], columns[row[3]])
        for row in names
    ]


def _shares(slots: list[tuple[list[np.ndarray], np.ndarray]], rows: range) -> dict[Colour, float]:
    """Mean share of each colour over the chunks `rows`, counting a chunk without it as 0."""
    total: dict[Colour, float] = {}
    for rgb, share in slots:
        for row in rows:
            held = float(share[row])
            if not np.isfinite(held) or held <= 0.0:
                continue
            colour = (
                int(round(rgb[0][row] * _BYTE)),
                int(round(rgb[1][row] * _BYTE)),
                int(round(rgb[2][row] * _BYTE)),
            )
            total[colour] = total.get(colour, 0.0) + held
    return {colour: held / len(rows) for colour, held in total.items()}


def _ranked(shares: dict[Colour, float]) -> list[tuple[Colour, float]]:
    return sorted(shares.items(), key=lambda item: (-item[1], item[0]))


def _column(index: int, count: int, shares: dict[Colour, float]) -> StripColumn:
    width = WIDTH / count
    y = TOP
    segments = []
    for colour, share in _ranked(shares)[:PALETTE_SIZE]:
        segments.append(Segment(_hex(colour), y, share * HEIGHT))
        y += share * HEIGHT
    return StripColumn(index * width, width, tuple(segments))


def build_palette(columns: Columns) -> PaletteView | None:
    """None when the store holds no palette (a run from before it, or a film with no chunks)."""
    slots = _slots(columns)
    count = len(next(iter(columns.values()))) if columns else 0
    if slots is None or count == 0:
        return None
    shown = min(count, MAX_COLUMNS)
    strip = tuple(
        _column(i, shown, _shares(slots, range(i * count // shown, (i + 1) * count // shown)))
        for i in range(shown)
    )
    overall = _ranked(_shares(slots, range(count)))[:SWATCHES]
    swatches = tuple(Swatch(_hex(c), number_text(_PERCENT * s, 0)) for c, s in overall)
    dark = ""
    if PALETTE_DARK in columns:
        mean = float(np.nanmean(np.asarray(columns[PALETTE_DARK], dtype=np.float64)))
        dark = number_text(_PERCENT * mean, 0)
    return PaletteView(TOP, HEIGHT, WIDTH, strip, swatches, dark)
