"""The command line: exit codes follow the error taxonomy, messages come from strings.toml, and a
second run with the same output folder resumes instead of starting over."""

from pathlib import Path

import pytest

from filmanalyser.cli.main import main
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
