"""Chart geometry: values in, coordinates inside the plot area out. Pure numbers; the template
draws them."""

import numpy as np

from filmanalyser.report.charts import (
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
