"""The view model turns stored columns and the analysis results into display-ready values.
Pure: arrays in, values out; no formatting for a language, no resource reads."""

import re

import numpy as np
import pytest

from filmanalyser.core import features as f
from filmanalyser.report.viewmodel import ReportView, build_view
from tests.fixtures.timelines import golden_film, timeline

CHUNK_KEYS = {"found": "act.zone.found", "empty": "act.zone.empty", "short": "act.zone.too_short"}


def view(columns: dict[str, np.ndarray] | None = None, film: str = "film.mp4") -> ReportView:
    return build_view(columns if columns is not None else golden_film(), film=film)


def test_overview_numbers_come_from_the_stored_cuts() -> None:
    cols = timeline(3, {f.CUT_COUNT: np.array([1.0, 0.0, 3.0]), f.GRADUAL_COUNT: 0.0})
    shown = view(cols).overview
    assert shown.total_cuts == 4
    assert shown.average_shot_text == "36.0"  # 180 s of film in 5 shots
    assert shown.mean_rate_text == "1.3"  # (1 + 0 + 3) cuts over 3 minutes


def test_a_film_with_no_cuts_has_one_long_shot() -> None:
    shown = view(timeline(3, {f.CUT_COUNT: 0.0, f.GRADUAL_COUNT: 0.0})).overview
    assert (shown.total_cuts, shown.average_shot_text) == (0, "180.0")


def test_the_film_header_states_length_and_chunks() -> None:
    shown = view()
    assert (shown.length_text, shown.chunk_count, shown.film) == ("1:40:00", 100, "film.mp4")


def test_the_film_name_is_carried_unchanged_for_the_view_to_escape() -> None:
    assert view(film="<b>x</b>.mp4").film == "<b>x</b>.mp4"


def test_breaks_carry_a_time_a_share_a_score_and_the_features_that_moved() -> None:
    first, second = view().acts.breaks
    assert (first.time_text, first.percent_text) == ("25:00", "25")
    assert (second.time_text, second.percent_text) == ("1:15:00", "75")
    assert first.score_text == "1.51"
    assert first.moved_keys == ("feature.color.colourfulness", "feature.color.warmth")


def test_acts_are_spans_between_the_breaks() -> None:
    spans = view().acts.spans
    assert [(s.number, s.start_text, s.end_text) for s in spans] == [
        (1, "0:00", "25:00"),
        (2, "25:00", "1:15:00"),
        (3, "1:15:00", "1:40:00"),
    ]


def test_a_zone_with_a_break_says_where() -> None:
    zones = view().acts.zones
    assert [(z.number, z.key, z.time_text) for z in zones] == [
        (1, CHUNK_KEYS["found"], "25:00"),
        (2, CHUNK_KEYS["found"], "1:15:00"),
    ]


def test_a_zone_judged_with_nothing_found_reads_no_break() -> None:
    zones = view(timeline(100)).acts.zones
    assert [z.key for z in zones] == [CHUNK_KEYS["empty"]] * 2
    assert view(timeline(100)).acts.breaks == ()


def test_a_zone_a_short_film_cannot_judge_is_not_called_empty() -> None:
    zones = view(timeline(12)).acts.zones
    assert [z.key for z in zones] == [CHUNK_KEYS["short"]] * 2
    assert {z.needs_text for z in zones} == {"13:00"}


def test_the_act_section_states_whether_audio_was_used() -> None:
    assert view().acts.audio_key == "act.audio.used"
    assert view(timeline(100, audio=False)).acts.audio_key == "act.audio.not_used"
    assert view().audio_used is True and view(timeline(100, audio=False)).audio_used is False


def test_the_features_used_are_listed_by_label_key() -> None:
    assert view().acts.feature_keys[0] == "feature.cut_rate"
    assert "feature.loudness.integrated_lufs" in view().acts.feature_keys
    assert (
        "feature.loudness.integrated_lufs" not in view(timeline(100, audio=False)).acts.feature_keys
    )


def test_the_tension_peak_is_reported_with_its_time_and_height() -> None:
    peak = view().tension.peak
    assert peak is not None
    assert (peak.time_text, peak.height_text) == ("1:00:00", "3.5")
    assert view().tension.component_keys == ("feature.cut_rate", "feature.loudness.integrated_lufs")


def test_no_peak_is_an_explicit_absence_not_a_blank() -> None:
    assert view(timeline(100)).tension.peak is None


def test_plateaus_are_listed_with_their_span_and_rate() -> None:
    rows = view().pacing.plateaus
    assert [(p.start_text, p.end_text, p.rate_text) for p in rows] == [
        ("40:00", "49:00", "10.3"),
        ("1:25:00", "1:31:00", "1.0"),
    ]


def test_every_flag_carries_a_timestamp_a_rule_and_a_value() -> None:
    rows = view().flags
    assert [r.kind_key for r in rows] == [
        "flag.kind.quiet",
        "flag.kind.clipping",
        "flag.kind.fast_cutting",
        "flag.kind.loud",
        "flag.kind.long_take",
    ]
    for row in rows:
        assert re.fullmatch(r"(\d+:)?\d+:\d\d", row.start_text)
        assert re.fullmatch(r"(\d+:)?\d+:\d\d", row.end_text)
        assert row.value_key.startswith("flag.value.") and row.value_text
    assert rows[0].start_text == "10:00"


def test_no_flags_is_an_empty_tuple() -> None:
    assert view(timeline(100)).flags == ()


def test_the_charts_cover_what_the_acceptance_list_names() -> None:
    keys = [c.key for c in view().charts]
    assert keys == [
        "chart.cut_rate",
        "chart.tension",
        "chart.loudness",
        "chart.mix",
        "chart.picture",
    ]


def test_a_film_without_audio_has_no_loudness_or_mix_chart() -> None:
    keys = [c.key for c in view(timeline(100, audio=False)).charts]
    assert keys == ["chart.cut_rate", "chart.tension", "chart.picture"]


def test_the_cut_rate_chart_marks_the_breaks_and_shades_the_plateaus() -> None:
    chart = view().charts[0]
    assert [m.kind for m in chart.markers].count("break") == 2
    assert len(chart.bands) == 2


def test_the_tension_chart_marks_the_peak() -> None:
    assert "peak" in [m.kind for m in view().charts[1].markers]


def test_an_empty_store_gives_an_empty_report() -> None:
    shown = view(timeline(0))
    assert shown.chunk_count == 0 and shown.charts == ()
    assert shown.length_text == "0:00" and shown.overview.total_cuts == 0
    assert shown.acts.breaks == () and shown.acts.spans == ()


def test_every_text_value_is_plain_ascii_digits_with_a_point() -> None:
    shown = view()
    texts = [
        shown.length_text,
        shown.overview.average_shot_text,
        shown.overview.mean_rate_text,
        shown.acts.breaks[0].score_text,
        shown.pacing.mean_rate_text,
    ]
    assert all(re.fullmatch(r"[0-9:.]+", t) for t in texts)


def test_the_same_columns_give_the_same_view() -> None:
    assert view() == view()


@pytest.mark.parametrize("count", [1, 2, 5, 13])
def test_very_short_films_build_without_error(count: int) -> None:
    assert view(timeline(count)).chunk_count <= count
