"""The whole product on a synthetic film with known structure, through the orchestration the
command uses: every ACCEPTANCE output metric is in the report, every flag carries a timestamp, the
features are versioned Parquet, and a second run reads the store without decoding the film."""

import json
import re
from pathlib import Path

import pyarrow.parquet as pq
import pytest

from filmanalyser.cli.args import parse_args
from filmanalyser.cli.run import run
from filmanalyser.core.config import Config
from filmanalyser.report.resources.strings import Strings
from tests.fixtures.make_synthetic import make_av_clip

STRINGS = Strings.load()
CONFIG = Config(chunk_seconds=1.0, overlap_seconds=0.25, analysis_fps=12.0, frame_width=64)
TONE = "0.5*sin(2*PI*440*t)*between(t\\,12\\,28)"
SECTIONS = (
    "section.overview",
    "section.charts",
    "section.acts",
    "section.tension",
    "section.pacing",
    "section.flags",
    "overview.total_cuts",
    "overview.average_shot",
    "chart.cut_rate.label",
    "chart.picture.label",
    "chart.loudness.label",
    "chart.mix.label",
    "chart.tension.label",
)


@pytest.fixture(scope="module")
def result(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, Path, str]:
    root = tmp_path_factory.mktemp("full")
    film = make_av_clip(root / "film.mp4", 40.0, TONE, flat=True)
    out = root / "out"
    options = parse_args([str(film), "--out", str(out)], STRINGS)
    message = run(options, STRINGS, CONFIG)
    return film, out, message


def test_the_report_holds_every_metric_section(result: tuple[Path, Path, str]) -> None:
    page = (result[1] / "report.html").read_text(encoding="utf-8")
    for key in SECTIONS:
        assert STRINGS.text(key) in page, key
    assert page.count("<svg") >= 5


def test_the_message_names_the_film_and_the_report(result: tuple[Path, Path, str]) -> None:
    assert "film.mp4" in result[2] and "report.html" in result[2]


def test_every_flag_row_carries_a_timestamp(result: tuple[Path, Path, str]) -> None:
    page = (result[1] / "report.html").read_text(encoding="utf-8")
    table = page.split(STRINGS.text("section.flags"), 1)[1]
    rows = re.findall(r"<tr><td>(.*?)</td>", table)
    assert rows
    assert all(re.search(r"\d+:\d\d", row) for row in rows)


def test_features_are_stored_as_versioned_parquet(result: tuple[Path, Path, str]) -> None:
    out = result[1]
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["complete"] is True and manifest["feature_version"]
    chunk = pq.read_table(out / "chunk_000000.parquet")
    assert any(name.startswith("shot_cuts.") for name in chunk.column_names)
    assert chunk.schema.metadata is not None
    assert b"filmanalyser.feature_version" in chunk.schema.metadata


def test_re_analysis_does_not_decode_the_film_again(
    result: tuple[Path, Path, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    film, out, _ = result

    def no_decode(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("the film was decoded again")

    monkeypatch.setattr("filmanalyser.pipeline.runner.decode_chunks", no_decode)
    options = parse_args(
        [str(film), "--out", str(out), "--report", str(out / "again.html")], STRINGS
    )
    run(options, STRINGS, CONFIG)
    assert (out / "again.html").read_text(encoding="utf-8") == (out / "report.html").read_text(
        encoding="utf-8"
    )
