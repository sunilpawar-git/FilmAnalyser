"""Argument parsing: defaults, the output folder's default name, and the flags."""

from pathlib import Path

import pytest

from filmanalyser.cli.args import Options, parse_args
from filmanalyser.report.resources.layout import DEFAULT_OUT_SUFFIX, REPORT_FILE
from filmanalyser.report.resources.strings import Strings

STRINGS = Strings.load()


def test_only_the_film_is_required() -> None:
    options = parse_args(["film.mp4"], STRINGS)
    assert isinstance(options, Options)
    assert options.film == Path("film.mp4")
    assert options.fresh is False and options.verbose is False and options.separate_voices is False


def test_the_output_folder_defaults_to_the_films_name_in_the_working_folder() -> None:
    options = parse_args(["/some/where/My Film.mp4"], STRINGS)
    assert options.out == Path(f"My Film{DEFAULT_OUT_SUFFIX}")


def test_the_report_defaults_to_the_output_folder() -> None:
    options = parse_args(["f.mp4", "--out", "work/f"], STRINGS)
    assert options.out == Path("work/f")
    assert options.report == Path("work/f") / REPORT_FILE


def test_an_explicit_report_is_kept() -> None:
    options = parse_args(["f.mp4", "--report", "r.html"], STRINGS)
    assert options.report == Path("r.html")


def test_flags() -> None:
    options = parse_args(["f.mp4", "--fresh", "-v", "--separate-voices"], STRINGS)
    assert options.fresh and options.verbose and options.separate_voices


def test_version_prints_the_name_and_version(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as stop:
        parse_args(["--version"], STRINGS)
    assert stop.value.code == 0
    assert capsys.readouterr().out.startswith("filmanalyser 0.")


def test_a_missing_film_is_a_usage_error(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as stop:
        parse_args([], STRINGS)
    assert stop.value.code == 2
    assert "film" in capsys.readouterr().err
