"""Input path validation and tool lookup: the first security boundary before any subprocess."""

import os
from pathlib import Path

import pytest

from filmanalyser.core.errors import DecodeError, InputError
from filmanalyser.media.paths import find_tool, scrub_stderr, validate_input_path


def _film(tmp_path: Path, name: str = "film.mp4") -> Path:
    path = tmp_path / name
    path.write_bytes(b"not really a film")
    return path


def test_valid_file_is_returned_resolved_and_absolute(tmp_path: Path) -> None:
    resolved = validate_input_path(_film(tmp_path))
    assert resolved.is_absolute()
    assert resolved == (tmp_path / "film.mp4").resolve()


def test_accepts_str_and_relative_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _film(tmp_path)
    monkeypatch.chdir(tmp_path)
    assert validate_input_path("film.mp4") == (tmp_path / "film.mp4").resolve()


def test_missing_file_is_an_input_error_naming_only_the_basename(tmp_path: Path) -> None:
    with pytest.raises(InputError) as info:
        validate_input_path(tmp_path / "nope.mp4")
    assert info.value.key == "error.input.not_found"
    assert info.value.fields == {"name": "nope.mp4"}
    assert str(tmp_path) not in str(info.value)


def test_directory_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(InputError) as info:
        validate_input_path(tmp_path)
    assert info.value.key == "error.input.not_a_file"


def test_unreadable_file_is_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Simulated, not chmod-based: root can read any file, so a chmod test would silently skip."""
    path = _film(tmp_path)
    monkeypatch.setattr(os, "access", lambda _p, _mode: False)
    with pytest.raises(InputError) as info:
        validate_input_path(path)
    assert info.value.key == "error.input.unreadable"


@pytest.mark.parametrize("raw", ["", "   ", "film\x00.mp4"])
def test_empty_or_nul_paths_are_rejected(raw: str) -> None:
    with pytest.raises(InputError) as info:
        validate_input_path(raw)
    assert info.value.key == "error.input.invalid_path"


def test_dash_leading_name_cannot_become_an_option(tmp_path: Path) -> None:
    """Option injection: `-i`, `-f` ... as a file name resolve to an absolute path."""
    resolved = validate_input_path(_film(tmp_path, "-f.mp4"))
    assert not resolved.name.startswith("/")
    assert str(resolved).startswith("/")  # ffmpeg can never read it as an option


def test_symlink_is_resolved_to_its_target(tmp_path: Path) -> None:
    target = _film(tmp_path)
    link = tmp_path / "link.mp4"
    link.symlink_to(target)
    assert validate_input_path(link) == target.resolve()


def test_symlink_loop_is_an_input_error(tmp_path: Path) -> None:
    loop = tmp_path / "loop.mp4"
    loop.symlink_to(loop)
    with pytest.raises(InputError) as info:
        validate_input_path(loop)
    assert info.value.key == "error.input.invalid_path"


def test_find_tool_returns_an_absolute_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    tool = tmp_path / "ffmpeg"
    tool.write_text("#!/bin/sh\n")
    tool.chmod(0o755)
    monkeypatch.setenv("PATH", str(tmp_path))
    assert find_tool("ffmpeg") == str(tool)


def test_missing_ffmpeg_is_a_decode_error(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("PATH", str(tmp_path))  # an empty directory
    with pytest.raises(DecodeError) as info:
        find_tool("ffmpeg")
    assert info.value.key == "error.decode.tool_missing"
    assert info.value.fields == {"tool": "ffmpeg"}


def test_scrub_stderr_bounds_output_and_hides_full_paths(tmp_path: Path) -> None:
    film = tmp_path / "secret_dir" / "film.mp4"
    raw = (f"error opening {film}\n" + "x" * 10_000).encode()
    text = scrub_stderr(raw, film, limit=200)
    assert len(text) <= 200
    assert str(tmp_path) not in text
    assert "film.mp4" in text or text.endswith("x")


def test_scrub_stderr_survives_invalid_utf8(tmp_path: Path) -> None:
    assert isinstance(scrub_stderr(b"\xff\xfe bad", tmp_path / "f.mp4", limit=50), str)


def test_unsearchable_directory_is_reported_as_unreadable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Simulated: resolving through an unsearchable directory raises PermissionError."""
    film = _film(tmp_path)
    real_resolve = Path.resolve

    def denied(self: Path, strict: bool = False) -> Path:
        if self == film:
            raise PermissionError(13, "denied")
        return real_resolve(self, strict=strict)

    monkeypatch.setattr(Path, "resolve", denied)
    with pytest.raises(InputError) as info:
        validate_input_path(film)
    assert info.value.key == "error.input.unreadable"
