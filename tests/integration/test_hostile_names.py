"""Security audit (Phase 8) as tests: a film's name is attacker-controlled text. Through the real
command it must not reach a shell, be read as an ffmpeg option, escape the output folder, or turn
into markup in the report."""

import re
import shutil
from pathlib import Path

import pytest

from filmanalyser.cli.main import main
from tests.fixtures.make_synthetic import make_cut_clip


@pytest.fixture(scope="module")
def source(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return make_cut_clip(tmp_path_factory.mktemp("hostile") / "src.mp4", [("red", 2.0)], fps=12)


def _copy(source: Path, folder: Path, name: str) -> Path:
    target = folder / name
    shutil.copyfile(source, target)
    return target


def test_shell_metacharacters_in_the_name_run_nothing(source: Path, tmp_path: Path) -> None:
    film = _copy(source, tmp_path, "$(touch PWNED); `touch PWNED2` & touch PWNED3 #.mp4")
    assert main([str(film), "--out", str(tmp_path / "out")]) == 0
    assert not list(tmp_path.glob("PWNED*"))
    assert not list(Path.cwd().glob("PWNED*"))


def test_a_name_that_looks_like_an_ffmpeg_option_is_only_a_file(
    source: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _copy(source, tmp_path, "-i.mp4")
    monkeypatch.chdir(tmp_path)
    assert main(["--out", str(tmp_path / "out"), "--", "-i.mp4"]) == 0


def test_the_film_name_is_escaped_in_the_report(source: Path, tmp_path: Path) -> None:
    film = _copy(source, tmp_path, "<img src=x onerror=alert(1)>\"'.mp4")
    out = tmp_path / "out"
    assert main([str(film), "--out", str(out)]) == 0
    page = (out / "report.html").read_text(encoding="utf-8")
    assert "<img src=x" not in page and "onerror=alert(1)>" not in page
    assert "&lt;img src=x onerror=alert(1)&gt;" in page


def test_nothing_is_written_outside_the_output_folder(source: Path, tmp_path: Path) -> None:
    film = _copy(source, tmp_path, "..%2f..%2fescape.mp4")
    out = tmp_path / "work" / "out"
    assert main([str(film), "--out", str(out)]) == 0
    before = {p.name for p in tmp_path.iterdir()}
    assert before == {film.name, "work"}
    assert all(
        re.fullmatch(r"manifest\.json|report\.html|chunk_\d{6}\.parquet", p.name)
        for p in out.iterdir()
    )


def test_a_symlinked_film_is_analysed_under_its_real_name(source: Path, tmp_path: Path) -> None:
    link = tmp_path / "link.mp4"
    link.symlink_to(source)
    out = tmp_path / "out"
    assert main([str(link), "--out", str(out)]) == 0
    assert "src.mp4" in (out / "report.html").read_text(encoding="utf-8")


def test_a_terminal_escape_in_the_name_never_reaches_the_screen(
    source: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    name = "a\x1b[2Jb\nforged line.mp4"
    film = _copy(source, tmp_path, name)
    assert main([str(film), "--out", str(tmp_path / "out")]) == 0
    shown = capsys.readouterr().out
    assert "\x1b" not in shown and shown.count("\n") == 1
    assert main([str(tmp_path / "gone\x1b[2J.mp4"), "--out", str(tmp_path / "o2")]) == 2
    assert "\x1b" not in capsys.readouterr().err
