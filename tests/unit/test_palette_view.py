"""The palette strip and the film's dominant colours, built from the stored palette columns."""

import numpy as np

from filmanalyser.analysis.timeline import Columns
from filmanalyser.core import features as f
from filmanalyser.report.palette_view import MAX_COLUMNS, build_palette
from tests.fixtures.timelines import timeline

RED, BLUE = (224 / 255, 32 / 255, 32 / 255), (32 / 255, 32 / 255, 224 / 255)


def film(count: int, ranks: list[list[tuple[float, float, float, float]]]) -> Columns:
    """`count` chunks; `ranks[r]` is (red, green, blue, share) of palette slot r+1, constant."""
    cols = timeline(count)
    slots = [r[0] for r in ranks] + [(0.0, 0.0, 0.0, 0.0)] * (3 - len(ranks))  # unused: empty
    for rank, values in enumerate(slots, 1):
        for part, value in zip(("red", "green", "blue", "share"), values, strict=True):
            cols[f"{f.COLOR}.palette_{rank}_{part}"] = np.full(count, value)
    return cols


def test_the_near_black_share_is_the_average_over_the_film() -> None:
    cols = dict(film(4, [[(*RED, 0.5)]]))
    cols[f.PALETTE_DARK] = np.array([0.2, 0.4, 0.6, 0.8])
    view = build_palette(cols)
    assert view is not None
    assert view.dark_text == "50"


def test_a_store_made_without_the_near_black_column_still_has_a_palette() -> None:
    view = build_palette(film(2, [[(*RED, 0.5)]]))
    assert view is not None
    assert view.dark_text == ""


def test_a_store_without_a_palette_has_no_palette_view() -> None:
    assert build_palette(timeline(5)) is None


def test_the_film_palette_ranks_colours_by_their_average_share() -> None:
    cols = film(4, [[(*RED, 0.6)], [(*BLUE, 0.3)]])
    view = build_palette(cols)
    assert view is not None
    assert [s.fill for s in view.swatches] == ["#e02020", "#2020e0"]
    assert [s.share_text for s in view.swatches] == ["60", "30"]


def test_a_colour_that_is_empty_is_not_a_swatch() -> None:
    view = build_palette(film(3, [[(*RED, 1.0)], [(0.0, 0.0, 0.0, 0.0)]]))
    assert view is not None
    assert [s.fill for s in view.swatches] == ["#e02020"]


def test_the_strip_has_one_column_per_chunk_up_to_a_limit() -> None:
    small = build_palette(film(5, [[(*RED, 1.0)]]))
    large = build_palette(film(MAX_COLUMNS * 3, [[(*RED, 1.0)]]))
    assert small is not None and large is not None
    assert len(small.columns) == 5
    assert len(large.columns) == MAX_COLUMNS


def test_a_column_stacks_its_colours_by_share_from_the_top() -> None:
    view = build_palette(film(2, [[(*RED, 0.75)], [(*BLUE, 0.25)]]))
    assert view is not None
    first = view.columns[0]
    assert [s.fill for s in first.segments] == ["#e02020", "#2020e0"]
    assert first.segments[0].y == view.top
    assert first.segments[0].height == 0.75 * view.height
    assert first.segments[1].y == first.segments[0].y + first.segments[0].height


def test_a_merged_column_averages_the_chunks_it_covers() -> None:
    count = MAX_COLUMNS * 2
    cols = film(count, [[(*RED, 1.0)]])
    cols[f"{f.COLOR}.palette_1_red"][:] = np.where(np.arange(count) % 2 == 0, RED[0], BLUE[0])
    cols[f"{f.COLOR}.palette_1_blue"][:] = np.where(np.arange(count) % 2 == 0, RED[2], BLUE[2])
    cols[f"{f.COLOR}.palette_1_green"][:] = RED[1]
    view = build_palette(cols)
    assert view is not None
    assert {s.fill for s in view.columns[0].segments} == {"#e02020", "#2020e0"}
    assert view.columns[0].segments[0].height == 0.5 * view.height


def test_a_nan_slot_is_ignored() -> None:
    cols = film(2, [[(*RED, 1.0)]])
    cols[f"{f.COLOR}.palette_1_share"][0] = np.nan
    view = build_palette(cols)
    assert view is not None
    assert view.columns[0].segments == ()
