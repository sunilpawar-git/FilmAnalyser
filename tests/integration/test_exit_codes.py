"""Every exit code of the taxonomy, through the real command (core/errors.py): the code, the
message from strings.toml, and no traceback. An unexpected failure is exit 1 with its own message;
an interrupt is 130 and says how to resume."""

import os
import stat
from pathlib import Path

import pytest

from filmanalyser.cli import run as run_module
from filmanalyser.cli.main import main
from filmanalyser.report.resources.strings import Strings
from tests.fixtures.make_synthetic import make_cut_clip

STRINGS = Strings.load()


@pytest.fixture(scope="module")
def film(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return make_cut_clip(tmp_path_factory.mktemp("codes") / "film.mp4", [("red", 2.0)], fps=12)


def _run(film: Path, out: Path, *extra: str) -> int:
    return main([str(film), "--out", str(out), *extra])


def test_success_is_zero(film: Path, tmp_path: Path) -> None:
    assert _run(film, tmp_path / "out") == 0


def test_a_missing_film_is_2(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert _run(tmp_path / "nope.mp4", tmp_path / "out") == 2
    assert "does not exist" in capsys.readouterr().err


def test_a_folder_in_place_of_a_film_is_2(tmp_path: Path) -> None:
    assert _run(tmp_path, tmp_path / "out") == 2


def test_an_option_shaped_film_name_is_just_a_missing_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)
    assert main(["--out", str(tmp_path / "o"), "--", "-i evil.mp4"]) == 2
    assert "does not exist" in capsys.readouterr().err


def test_a_file_that_is_not_a_video_is_3(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    text = tmp_path / "notes.mp4"
    text.write_text("this is not a film")
    assert _run(text, tmp_path / "out") == 3
    assert "could not be inspected" in capsys.readouterr().err


def test_missing_ffmpeg_is_3(
    film: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("PATH", "")
    assert _run(film, tmp_path / "out") == 3
    assert "was not found" in capsys.readouterr().err


def test_a_bad_separation_model_is_4(
    film: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    tool = tmp_path / "bin" / "demucs"
    tool.parent.mkdir()
    tool.write_text("#!/bin/sh\nexit 0\n")
    tool.chmod(tool.stat().st_mode | stat.S_IXUSR)
    monkeypatch.setenv("PATH", f"{tool.parent}{os.pathsep}{os.environ['PATH']}")
    models = tmp_path / "models"
    models.mkdir()
    code = _run(film, tmp_path / "out", "--separate-voices", "--separation-model", str(models))
    assert code == 4
    assert "integrity check" in capsys.readouterr().err


def test_a_store_made_for_another_film_is_5(
    film: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    other = make_cut_clip(tmp_path / "other.mp4", [("blue", 2.0)], fps=12)
    assert _run(film, tmp_path / "out") == 0
    assert _run(other, tmp_path / "out") == 5
    assert "Use another output folder" in capsys.readouterr().err


def test_an_output_path_that_is_a_file_is_5(film: Path, tmp_path: Path) -> None:
    blocker = tmp_path / "out"
    blocker.write_text("a file")
    assert _run(film, blocker) == 5


def test_a_report_path_in_a_missing_folder_is_2(
    film: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = _run(film, tmp_path / "out", "--report", str(tmp_path / "no" / "such" / "r.html"))
    assert code == 2
    assert "cannot be written" in capsys.readouterr().err


def test_the_report_may_not_overwrite_the_film(film: Path, tmp_path: Path) -> None:
    before = film.read_bytes()
    assert _run(film, tmp_path / "out", "--report", str(film)) == 2
    assert film.read_bytes() == before


def test_the_report_may_not_be_a_link_to_the_film(film: Path, tmp_path: Path) -> None:
    before = film.read_bytes()
    link = tmp_path / "r.html"
    link.symlink_to(film)
    assert _run(film, tmp_path / "out", "--report", str(link)) == 2
    assert film.read_bytes() == before


def test_an_unexpected_failure_is_1_with_a_message_and_no_traceback(
    film: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def boom(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("secret internal detail")

    monkeypatch.setattr(run_module, "analyse", boom)
    assert _run(film, tmp_path / "out") == 1
    err = capsys.readouterr().err
    assert STRINGS.text("error.internal.default") in err
    assert "Traceback" not in err and "secret internal detail" not in err


def test_verbose_shows_the_traceback_of_an_unexpected_failure(
    film: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def boom(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("secret internal detail")

    monkeypatch.setattr(run_module, "analyse", boom)
    assert _run(film, tmp_path / "out", "-v") == 1
    assert "secret internal detail" in capsys.readouterr().err


def test_an_interrupt_is_130_and_says_how_to_resume(
    film: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def stop(*_args: object, **_kwargs: object) -> None:
        raise KeyboardInterrupt

    monkeypatch.setattr(run_module, "analyse", stop)
    assert _run(film, tmp_path / "out") == 130
    assert STRINGS.text("cli.interrupted") in capsys.readouterr().err
