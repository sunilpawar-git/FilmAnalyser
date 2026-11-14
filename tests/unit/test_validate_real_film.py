"""The validation script: it refuses a truth file the owner did not write, reads the films and
tolerances, converts memory units per platform, and runs a real film through the real command."""

import json
from pathlib import Path

import pytest

from filmanalyser.report.display import clock_text
from tests.fixtures.make_synthetic import make_av_clip
from validate_real_film import (
    FilmCase,
    load_cases,
    main,
    peak_mb,
    validate,
)
from validation_judge import Expected

FILM = {"title": "A", "film": "/f/a.mp4", "out": "/o/a", "act_breaks_s": [1800, 5400]}


def _truth(**extra: object) -> str:
    return json.dumps({"verified_by": "owner", "films": [FILM], **extra})


def test_a_truth_file_must_say_the_owner_wrote_it() -> None:
    films = json.dumps([FILM])
    for text in (f'{{"films": {films}}}', f'{{"verified_by": "an AI answer", "films": {films}}}'):
        with pytest.raises(ValueError, match="verified_by"):
            load_cases(text)


def test_a_file_with_no_times_needs_no_attestation() -> None:
    bare = {"title": "A", "film": "/f/a.mp4", "out": "/o/a"}
    cases, _, _ = load_cases(json.dumps({"films": [bare]}))
    assert cases[0].expected == Expected((), None)


def test_the_films_and_the_default_tolerance_are_read() -> None:
    cases, tol, climax_tol = load_cases(_truth())
    assert (tol, climax_tol) == (300.0, 300.0)
    assert cases[0].expected == Expected((1800.0, 5400.0), None)
    assert cases[0].held_out is False and cases[0].film == Path("/f/a.mp4")


def test_the_tolerances_and_the_held_out_flag_are_editable() -> None:
    held = {**FILM, "held_out": True, "climax_s": 6000}
    text = json.dumps(
        {"verified_by": "owner", "tolerance_s": 120, "climax_tolerance_s": 600, "films": [held]}
    )
    cases, tol, climax_tol = load_cases(text)
    assert (tol, climax_tol) == (120.0, 600.0)
    assert cases[0].held_out and cases[0].expected.climax_s == 6000.0


def test_peak_memory_is_bytes_on_macos_and_kilobytes_elsewhere() -> None:
    assert peak_mb(2 * 1024 * 1024, "Darwin") == 2.0
    assert peak_mb(2048, "Linux") == 2.0


def test_main_without_a_file_prints_usage_and_a_refused_file_exits_1(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["validate_real_film.py"]) == 2
    bad = tmp_path / "truth.json"
    bad.write_text(json.dumps({"films": [FILM]}), encoding="utf-8")
    assert main(["validate_real_film.py", str(bad)]) == 1
    assert "verified_by" in capsys.readouterr().err


def test_a_real_run_measures_memory_and_time_and_judges_the_film(tmp_path: Path) -> None:
    film = make_av_clip(tmp_path / "film.mp4", 6.0, "0.3*sin(2*PI*440*t)", flat=True)
    case = FilmCase("Synthetic", film, tmp_path / "store", False, Expected((), None))
    lines = validate([case], 300.0, 300.0, fresh=True)
    row = next(line for line in lines if line.startswith("| Synthetic"))
    assert clock_text(6.0) in row and "MB (yes)" in row
    assert any("not applicable yet" in line for line in lines)
    kept = validate([case], 300.0, 300.0, fresh=False)
    assert "not measured" in next(line for line in kept if line.startswith("| Synthetic"))


def test_a_failing_command_is_reported_in_the_table(tmp_path: Path) -> None:
    case = FilmCase("Missing", tmp_path / "nope.mp4", tmp_path / "s", False, Expected((), None))
    lines = validate([case], 300.0, 300.0, fresh=True)
    assert any("exited with code 2" in line for line in lines)
