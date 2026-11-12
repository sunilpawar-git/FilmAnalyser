"""The static report: escaped output, no scripts or external requests, colours only from tokens,
and every piece of visible text from strings.toml."""

import re

import numpy as np
import pytest

from filmanalyser.report.renderer import render_report
from filmanalyser.report.resources.colors import ColorTokens
from filmanalyser.report.resources.strings import Strings
from filmanalyser.report.viewmodel import ReportView, build_view


def _view(film: str = "film.mp4") -> ReportView:
    cols = {
        "chunk_index": np.arange(2, dtype=np.int32),
        "start_s": np.array([0.0, 10.0]),
        "end_s": np.array([10.0, 20.0]),
        "shot_cuts.cuts": np.array([1.0, 2.0]),
        "shot_cuts.max_diff": np.zeros(2),
    }
    return build_view(cols, film=film)


@pytest.fixture(scope="module")
def html() -> str:
    return render_report(_view(), Strings.load(), ColorTokens.load())


def test_the_page_is_a_full_document(html: str) -> None:
    assert html.startswith("<!doctype html>")
    assert "</html>" in html


def test_a_strict_content_security_policy_forbids_network_and_scripts(html: str) -> None:
    assert re.search(r"Content-Security-Policy.*default-src 'none'", html)


def test_the_chart_is_inline_svg_with_a_line(html: str) -> None:
    assert "<svg" in html and "<polyline" in html


def test_no_script_or_external_resource_is_referenced(html: str) -> None:
    assert "<script" not in html.lower()
    assert not re.search(r'(src|href)="https?://', html)


def test_the_film_name_is_escaped_not_injected() -> None:
    page = render_report(
        _view("<img src=x onerror=alert(1)>.mp4"), Strings.load(), ColorTokens.load()
    )
    assert "<img src=x" not in page
    assert "&lt;img src=x" in page


def test_colour_values_appear_only_in_the_token_block(html: str) -> None:
    tokens = ColorTokens.load()
    body = re.sub(r"<style>.*?</style>", "", html, flags=re.DOTALL)
    assert not re.search(r"#[0-9a-fA-F]{6}\b", body)
    assert "var(--text)" in html  # the styles use the tokens, inside <style>
    assert f"--background: {tokens.light['background']};" in html


def test_visible_text_comes_from_the_strings_table(html: str) -> None:
    strings = Strings.load()
    assert strings.text("report.title") in html
    assert strings.text("app.tagline") in html
