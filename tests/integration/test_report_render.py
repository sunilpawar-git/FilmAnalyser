"""The report for a clip the pipeline really analysed: the page renders from stored features, says
what the analysis could and could not judge, escapes the film's name, makes no external request and
uses colour only through tokens."""

import re
from pathlib import Path

import pytest

from filmanalyser.core.config import Config
from filmanalyser.pipeline.runner import analyse
from filmanalyser.report.renderer import render_report
from filmanalyser.report.resources.colors import ColorTokens
from filmanalyser.report.resources.strings import Strings
from filmanalyser.report.viewmodel import build_view
from tests.fixtures.make_synthetic import make_av_clip, make_silent_clip

CONFIG = Config(chunk_seconds=1.0, overlap_seconds=0.25, analysis_fps=12.0, frame_width=64)
TONE = "0.5*sin(2*PI*440*t)*between(t\\,12\\,28)"
STRINGS = Strings.load()
CHARTS = ("cut_rate", "tension", "loudness", "mix", "picture")


def _page(film: Path, out: Path, name: str | None = None) -> str:
    columns = analyse(film, out, CONFIG).read_columns()
    view = build_view(columns, film=name or film.name)
    return render_report(view, STRINGS, ColorTokens.load())


@pytest.fixture(scope="module")
def page(tmp_path_factory: pytest.TempPathFactory) -> str:
    root = tmp_path_factory.mktemp("report")
    film = make_av_clip(root / "a&b.mp4", 40.0, TONE, flat=True)
    return _page(film, root / "store")


def test_a_real_clip_gives_every_chart_and_the_unvalidated_notice(page: str) -> None:
    assert page.count("<svg") == len(CHARTS)
    assert "P6-1" in page and "P6-2" in page


def test_the_film_name_is_escaped(page: str) -> None:
    assert "a&amp;b.mp4" in page and "a&b.mp4" not in page


def test_the_act_section_says_sound_was_used(page: str) -> None:
    assert STRINGS.text("act.audio.used") in page


def test_the_page_is_self_contained(page: str) -> None:
    assert "<script" not in page.lower()
    assert not re.search(r"https?://|url\(|@import|(src|href)\s*=", page)
    assert "default-src 'none'" in page


def test_colour_appears_only_as_tokens(page: str) -> None:
    body = re.sub(r":root \{[^}]*\}", "", page)
    assert not re.search(r"#[0-9a-fA-F]{3,8}\b|\brgba?\(|\bhsla?\(", body)


def test_a_film_too_short_to_judge_says_so_and_never_says_no_break(tmp_path: Path) -> None:
    film = make_av_clip(tmp_path / "short.mp4", 6.0, TONE)
    shown = _page(film, tmp_path / "store")
    assert "too short to judge (needs 0:13)" in shown
    assert STRINGS.text("act.zone.empty", zone=1) not in shown


def test_a_film_without_sound_says_so_and_draws_no_loudness_chart(tmp_path: Path) -> None:
    shown = _page(make_silent_clip(tmp_path / "silent.mp4", 40.0), tmp_path / "store")
    assert STRINGS.text("act.audio.not_used") in shown
    assert shown.count("<svg") == 3


def test_the_same_store_renders_the_same_page(tmp_path: Path) -> None:
    film = make_av_clip(tmp_path / "av.mp4", 20.0, TONE, flat=True)
    first = _page(film, tmp_path / "store")
    assert first == _page(film, tmp_path / "store")
