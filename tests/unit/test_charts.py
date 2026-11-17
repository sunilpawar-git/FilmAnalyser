"""Chart geometry: values in, coordinates inside the plot area out. Pure numbers; the template
draws them."""

import numpy as np

from filmanalyser.report.charts import (
    Chart,
    Frame,
    Marker,
    Notes,
    Series,
    Span,
    build_chart,
    nice_step,
)

MIDDLES = np.array([30.0, 90.0, 150.0, 210.0])  # four one-minute chunks of a four-minute film
FRAME = Frame(MIDDLES, 240.0)


def test_points_lie_inside_the_plot_area() -> None:
    shown = build_chart(
        "chart.cut_rate",
        FRAME,
        (Series("feature.cut_rate", "s1", np.array([0.0, 5.0, 2.0, 9.0])),),
    )
    for segment in shown.lines[0].segments:
        for pair in segment.split(" "):
            x, y = (float(v) for v in pair.split(","))
            assert shown.left <= x <= shown.right
            assert shown.top <= y <= shown.bottom


def test_the_highest_value_is_drawn_above_the_lowest() -> None:
    shown = build_chart("c", FRAME, (Series("l", "s1", np.array([1.0, 9.0, 1.0, 1.0])),))
    (segment,) = shown.lines[0].segments
    ys = [float(p.split(",")[1]) for p in segment.split(" ")]
    assert ys[1] < ys[0]  # SVG y grows downward


def test_a_missing_value_splits_the_line() -> None:
    shown = build_chart("c", FRAME, (Series("l", "s1", np.array([1.0, np.nan, 3.0, 4.0])),))
    assert len(shown.lines[0].segments) == 2


def test_a_series_with_nothing_measured_draws_no_line() -> None:
    shown = build_chart("c", FRAME, (Series("l", "s1", np.full(4, np.nan)),))
    assert shown.lines[0].segments == ()


def test_a_flat_series_still_has_a_range() -> None:
    shown = build_chart("c", FRAME, (Series("l", "s1", np.full(4, 2.0)),))
    assert shown.y_ticks[0].text != shown.y_ticks[-1].text


def test_a_fixed_range_is_honoured() -> None:
    shown = build_chart(
        "c", FRAME, (Series("l", "s1", np.array([0.2, 0.4, 0.6, 0.8])),), y_range=(0.0, 1.0)
    )
    assert [t.text for t in shown.y_ticks] == ["0.0", "0.5", "1.0"]


def test_markers_and_bands_are_placed_on_the_film_clock() -> None:
    shown = build_chart(
        "c",
        FRAME,
        (Series("l", "s1", np.array([1.0, 2.0, 3.0, 4.0])),),
        notes=Notes(
            markers=(Marker(120.0, "break", "chart.mark.break", "2:00"),),
            bands=(Span(60.0, 180.0, "chart.mark.plateau"),),
        ),
    )
    mid = (shown.left + shown.right) / 2
    assert abs(shown.markers[0].x - mid) < 1e-6
    assert shown.markers[0].text == "2:00"
    assert shown.bands[0].width > 0 and shown.bands[0].x > shown.left
    assert [(e.label_key, e.kind) for e in shown.legend] == [
        ("chart.mark.break", "break"),
        ("chart.mark.plateau", "band"),
    ]


def test_time_ticks_are_whole_minutes_and_few() -> None:
    shown = build_chart("c", FRAME, (Series("l", "s1", np.arange(4.0)),))
    assert [t.text for t in shown.x_ticks] == ["0", "1", "2", "3", "4"]
    long = build_chart(
        "c", Frame(np.array([5000.0]), 10_000.0), (Series("l", "s1", np.array([1.0])),)
    )
    assert len(long.x_ticks) <= 9


def test_nice_step_grows_with_the_film() -> None:
    assert nice_step(4.0) == 1
    assert nice_step(95.0) == 15
    assert nice_step(600.0) > nice_step(95.0)


def stacked(values: list[list[float]]) -> Chart:
    series = tuple(Series(f"l{i}", f"a{i + 1}", np.array(v)) for i, v in enumerate(values))
    return build_chart("c", FRAME, series, y_range=(0.0, 1.0), notes=Notes(stacked=True))


def test_a_stacked_chart_draws_bands_and_no_lines() -> None:
    shown = stacked([[0.2] * 4, [0.3] * 4, [0.1] * 4])
    assert shown.lines == () and len(shown.areas) == 3


def test_each_band_lies_above_the_one_before_it() -> None:
    shown = stacked([[0.2] * 4, [0.3] * 4])
    first, second = (
        [tuple(float(v) for v in p.split(",")) for p in a.points.split(" ")] for a in shown.areas
    )
    top_of_first = min(y for _, y in first)
    bottom_of_second = max(y for _, y in second)
    assert abs(top_of_first - bottom_of_second) < 0.11  # they meet along one edge (rounded)
    assert min(y for _, y in second) < top_of_first  # the second sits higher on the page


def test_a_band_is_closed_and_inside_the_plot_area() -> None:
    shown = stacked([[0.0, 0.5, 1.0, 0.25]])
    points = [tuple(float(v) for v in p.split(",")) for p in shown.areas[0].points.split(" ")]
    assert len(points) == 8  # four along the top edge, four back along the bottom
    for x, y in points:
        assert shown.left <= x <= shown.right
        assert shown.top <= y <= shown.bottom


def test_a_missing_value_counts_as_nothing_in_a_stack() -> None:
    shown = stacked([[0.5, np.nan, 0.5, 0.5]])
    ys = [float(p.split(",")[1]) for p in shown.areas[0].points.split(" ")][:4]
    assert ys[1] == shown.bottom


def test_the_time_axis_title_clears_the_tick_labels() -> None:
    shown = build_chart("c", FRAME, (Series("l", "s1", np.array([1.0, 2.0, 3.0, 4.0])),))
    assert shown.axis_title_y - (shown.bottom + shown.tick_offset) >= 18.0
