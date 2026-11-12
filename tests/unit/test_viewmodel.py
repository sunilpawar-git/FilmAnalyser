"""The view model turns stored columns into display-ready numbers. Pure: arrays in, values out."""

import numpy as np

from filmanalyser.report.viewmodel import CHART_HEIGHT, CHART_WIDTH, build_view


def columns(cuts: list[float], spans: int = 3, chunk: float = 10.0) -> dict[str, np.ndarray]:
    starts = np.arange(spans) * chunk
    return {
        "chunk_index": np.arange(spans, dtype=np.int32),
        "start_s": starts,
        "end_s": starts + chunk,
        "shot_cuts.cuts": np.array(cuts, dtype=np.float64),
        "shot_cuts.max_diff": np.zeros(spans),
    }


def test_cut_rate_is_cuts_per_minute_for_each_chunk() -> None:
    view = build_view(columns([1, 0, 3]), film="film.mp4")
    assert [round(p.per_minute, 3) for p in view.cut_rate] == [6.0, 0.0, 18.0]


def test_totals_and_average_shot_length() -> None:
    view = build_view(columns([1, 0, 3]), film="film.mp4")
    assert view.total_cuts == 4
    assert view.film_seconds == 30.0
    assert view.average_shot_s == 6.0  # 30 s of film in 5 shots
    assert view.average_shot_text == "6.0"


def test_chart_points_lie_inside_the_chart_area() -> None:
    view = build_view(columns([2, 0, 5]), film="film.mp4")
    for point in view.cut_rate:
        assert 0.0 <= point.x <= CHART_WIDTH
        assert 0.0 <= point.y <= CHART_HEIGHT
    assert view.chart_points.count(" ") == 2  # three "x,y" pairs


def test_a_film_with_no_cuts_has_one_long_shot() -> None:
    view = build_view(columns([0, 0, 0]), film="film.mp4")
    assert view.total_cuts == 0
    assert view.average_shot_s == 30.0


def test_an_empty_store_gives_an_empty_report() -> None:
    view = build_view(columns([], spans=0), film="film.mp4")
    assert view.cut_rate == ()
    assert view.total_cuts == 0
    assert view.film_seconds == 0.0


def test_the_film_name_is_carried_unchanged_for_the_view_to_escape() -> None:
    name = "<b>x</b>.mp4"
    assert build_view(columns([1]), film=name).film == name
