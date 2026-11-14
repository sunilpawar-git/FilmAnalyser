"""The command line: exit codes follow the error taxonomy, messages come from strings.toml, and a
second run with the same output folder resumes instead of starting over."""

from pathlib import Path

import pytest

from filmanalyser.cli.main import main
from filmanalyser.report.resources.layout import DEFAULT_OUT_SUFFIX, REPORT_FILE
from tests.fixtures.make_synthetic import make_cut_clip


@pytest.fixture(scope="module")
def film(tmp_path_factory: pytest.TempPathFactory) -> Path:
    scenes = [("red", 2.0), ("blue", 2.0)]
    return make_cut_clip(tmp_path_factory.mktemp("cli") / "film.mp4", scenes, fps=12)


def test_a_run_writes_the_store_and_the_report(film: Path, tmp_path: Path) -> None:
    report = tmp_path / "report.html"
    code = main([str(film), "--out", str(tmp_path / "out"), "--report", str(report)])
    assert code == 0
    assert (tmp_path / "out" / "manifest.json").is_file()
    assert "<polyline" in report.read_text(encoding="utf-8")


def test_a_second_run_resumes_and_still_succeeds(film: Path, tmp_path: Path) -> None:
    out, report = tmp_path / "out", tmp_path / "report.html"
    assert main([str(film), "--out", str(out), "--report", str(report)]) == 0
    assert main([str(film), "--out", str(out), "--report", str(report)]) == 0


def test_resume_does_not_extract_a_finished_run_again(
    film: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    out = tmp_path / "out"
    assert main([str(film), "--out", str(out), "-v"]) == 0
    first = capsys.readouterr().err.count('"event": "chunk_extracted"')
    assert main([str(film), "--out", str(out), "-v"]) == 0
    assert first >= 1
    assert capsys.readouterr().err.count('"event": "chunk_extracted"') == 0


def test_fresh_starts_over_and_extracts_again(
    film: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    out = tmp_path / "out"
    assert main([str(film), "--out", str(out)]) == 0
    capsys.readouterr()
    assert main([str(film), "--out", str(out), "--fresh", "-v"]) == 0
    assert capsys.readouterr().err.count('"event": "chunk_extracted"') >= 1


def test_fresh_unblocks_a_folder_that_holds_another_films_store(film: Path, tmp_path: Path) -> None:
    other = make_cut_clip(tmp_path / "other.mp4", [("blue", 2.0)], fps=12)
    out = tmp_path / "out"
    assert main([str(other), "--out", str(out)]) == 0
    assert main([str(film), "--out", str(out)]) == 5
    assert main([str(film), "--out", str(out), "--fresh"]) == 0


def test_without_out_the_store_and_report_go_to_a_folder_named_after_the_film(
    film: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    assert main([str(film)]) == 0
    folder = tmp_path / f"film{DEFAULT_OUT_SUFFIX}"
    assert (folder / "manifest.json").is_file()
    assert (folder / REPORT_FILE).is_file()


def test_the_done_message_names_the_film_and_the_report(
    film: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main([str(film), "--out", str(tmp_path / "out")]) == 0
    out = capsys.readouterr().out
    assert "film.mp4" in out and "report.html" in out


def test_a_missing_film_exits_with_the_input_code_and_a_message(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = main([str(tmp_path / "nope.mp4"), "--out", str(tmp_path / "out")])
    assert code == 2
    assert "does not exist" in capsys.readouterr().err


def test_missing_ffmpeg_fails_loudly_with_the_decode_code(
    film: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("PATH", "")
    code = main([str(film), "--out", str(tmp_path / "out")])
    assert code == 3
    assert "'ffprobe' was not found" in capsys.readouterr().err  # probed first


def test_verbose_prints_structured_events_to_stderr(
    film: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = main(
        [str(film), "--out", str(tmp_path / "out"), "--report", str(tmp_path / "r.html"), "-v"]
    )
    assert code == 0
    events = [line for line in capsys.readouterr().err.splitlines() if line.startswith("{")]
    assert any('"event": "chunk_extracted"' in line for line in events)
