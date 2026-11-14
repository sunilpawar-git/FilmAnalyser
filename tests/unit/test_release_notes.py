"""The release notes come from CHANGELOG.md and only for the version in pyproject.toml."""

from pathlib import Path

import pytest

import release_notes
from release_notes import main, notes_for, project_version, section

PYPROJECT = '[project]\nname = "x"\nversion = "1.2.3"\n'
CHANGELOG = """## Unreleased

### Feat

- **a**: not yet

## 1.2.3 (2026-01-01)

### Feat

- **b**: shipped

## 1.2.2 (2025-12-01)

### Fix

- **c**: older
"""


def test_the_version_is_read_from_pyproject() -> None:
    assert project_version(PYPROJECT) == "1.2.3"


def test_the_section_is_the_text_under_its_heading_only() -> None:
    text = section(CHANGELOG, "1.2.3")
    assert text is not None
    assert "shipped" in text and "older" not in text and "not yet" not in text


def test_a_version_with_no_heading_has_no_section() -> None:
    assert section(CHANGELOG, "9.9.9") is None


def test_notes_for_the_matching_tag() -> None:
    assert "shipped" in notes_for("v1.2.3", PYPROJECT, CHANGELOG)


@pytest.mark.parametrize("tag", ["v1.2.4", "1.2.3", "vv1.2.3", "v1.2"])
def test_a_tag_that_is_not_the_project_version_is_refused(tag: str) -> None:
    with pytest.raises(ValueError, match="pyproject"):
        notes_for(tag, PYPROJECT, CHANGELOG)


def test_a_missing_or_empty_section_is_refused() -> None:
    with pytest.raises(ValueError, match="no entries"):
        notes_for("v1.2.3", PYPROJECT, "## Unreleased\n\n- x\n")
    with pytest.raises(ValueError, match="no entries"):
        notes_for("v1.2.3", PYPROJECT, "## 1.2.3\n\n## 1.2.2\n\n- y\n")


def test_main_needs_exactly_one_tag(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["release_notes.py"]) == 2
    assert "usage" in capsys.readouterr().err


def test_main_refuses_a_tag_that_is_not_the_version(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["release_notes.py", "v0.0.0"]) == 1
    assert "release_notes:" in capsys.readouterr().err


def test_main_prints_the_section_of_the_repository_files(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    (tmp_path / "pyproject.toml").write_text(PYPROJECT, encoding="utf-8")
    (tmp_path / "CHANGELOG.md").write_text(CHANGELOG, encoding="utf-8")
    monkeypatch.setattr(release_notes, "REPO", tmp_path)
    assert main(["release_notes.py", "v1.2.3"]) == 0
    assert capsys.readouterr().out.startswith("## 1.2.3")
