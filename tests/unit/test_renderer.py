"""The renderer: one escaped, self-contained page. Visible text comes from strings.toml and
colours from tokens (the architecture tests scan the templates; these render them)."""

import html as htmllib
import re

import pytest

from filmanalyser.report.renderer import render_report
from filmanalyser.report.resources.colors import ColorTokens
from filmanalyser.report.resources.strings import Strings
from filmanalyser.report.viewmodel import ReportView, build_view
from tests.fixtures.timelines import golden_film, timeline


def page(columns: object = None, film: str = "film.mp4") -> str:
    view: ReportView = build_view(columns if columns is not None else golden_film(), film=film)  # type: ignore[arg-type]
    return render_report(view, Strings.load(), ColorTokens.load())


@pytest.fixture(scope="module")
def html() -> str:
    return page()


def text(key: str, **fields: str) -> str:
    """The text as it appears in the page: autoescape turns an apostrophe into &#39;."""
    raw = htmllib.escape(Strings.load().text(key, **fields), quote=False)
    return raw.replace("'", "&#39;")


def test_the_page_is_a_full_document(html: str) -> None:
    assert html.startswith("<!doctype html>") and "</html>" in html


def test_the_unvalidated_notice_is_on_the_page(html: str) -> None:
    assert text("notice.unvalidated") in html
    assert "P6-1" in html and "P6-2" in html and "synthetic" in html


def test_the_notice_appears_before_any_finding(html: str) -> None:
    assert html.index(text("notice.unvalidated")) < html.index(text("section.acts"))


def test_the_film_name_is_escaped_not_injected() -> None:
    shown = page(film="<img src=x onerror=alert(1)>.mp4")
    assert "<img src=x" not in shown and "&lt;img src=x" in shown


def test_a_found_zone_names_its_break_and_audio_use_is_stated(html: str) -> None:
    assert text("act.audio.used") in html
    assert text("act.zone.found", zone="1", time="25:00") in html


def test_a_zone_too_short_to_judge_never_reads_no_break() -> None:
    shown = page(timeline(12))
    assert text("act.zone.too_short", zone="1", needs="13:00") in shown
    assert text("act.zone.empty", zone="1") not in shown


def test_a_zone_judged_empty_reads_no_break_found() -> None:
    shown = page(timeline(100))
    assert text("act.zone.empty", zone="2") in shown
    assert "too short to judge" not in shown


def test_a_film_without_sound_says_the_breaks_come_from_the_picture() -> None:
    assert text("act.audio.not_used") in page(timeline(100, audio=False))


def test_flags_peak_and_plateaus_are_listed_as_observations(html: str) -> None:
    assert text("flag.kind.clipping") in html
    assert text("tension.peak", time="1:00:00", height="3.5") in html
    assert "40:00" in html and "1:31:00" in html


def test_no_peak_and_no_flags_say_so() -> None:
    shown = page(timeline(100))
    assert text("tension.no_peak") in shown and text("flags.none") in shown


def test_every_chart_is_inline_svg_with_a_text_alternative(html: str) -> None:
    assert html.count("<svg") == 5
    for key in ("chart.cut_rate", "chart.tension", "chart.loudness", "chart.mix", "chart.picture"):
        assert f'aria-label="{text(key + ".label")}"' in html


def test_the_page_makes_no_external_request(html: str) -> None:
    assert "<script" not in html.lower()
    assert not re.search(r"(src|href|action|xlink:href)\s*=", html)
    assert not re.search(r"https?://|url\(|@import", html)


def test_a_strict_content_security_policy_forbids_everything_but_inline_style(html: str) -> None:
    match = re.search(r'Content-Security-Policy" content="([^"]*)"', html)
    assert match is not None
    assert match.group(1) == "default-src 'none'; style-src 'unsafe-inline'"


def test_colours_are_tokens_only_and_both_themes_are_defined(html: str) -> None:
    tokens = ColorTokens.load()
    body = re.sub(r"<style>.*?</style>", "", html, flags=re.DOTALL)
    assert not re.search(r"#[0-9a-fA-F]{3,8}\b|\brgba?\(|\bhsla?\(", body)
    css = re.search(r"<style>(.*?)</style>", html, flags=re.DOTALL)
    assert css is not None
    outside = re.sub(r":root \{[^}]*\}", "", css.group(1))
    assert not re.search(r"#[0-9a-fA-F]{3,8}\b|\brgba?\(|\bhsla?\(", outside)
    for name, value in tokens.light.items():
        assert f"--{name}: {value};" in html
    for name, value in tokens.dark.items():
        assert f"--{name}: {value};" in html
    assert "prefers-color-scheme: dark" in html


def test_every_var_reference_names_a_defined_token(html: str) -> None:
    defined = set(ColorTokens.load().light)
    used = set(re.findall(r"var\(--([a-z-]+)\)", html))
    assert used and used <= defined


def test_no_inline_style_attributes_or_event_handlers(html: str) -> None:
    assert not re.search(r"\sstyle\s*=", html)
    assert not re.search(r"\son[a-z]+\s*=", html)


def test_no_unresolved_placeholder_reaches_the_page(html: str) -> None:
    assert "$" not in re.sub(r"<style>.*?</style>", "", html, flags=re.DOTALL)
    assert "{{" not in html and "{%" not in html


def test_an_empty_store_still_renders() -> None:
    shown = page(timeline(0))
    assert "<svg" not in shown and text("report.empty") in shown
