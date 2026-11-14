"""The release notes for a `v*` tag, from CHANGELOG.md: `python scripts/release_notes.py vX.Y.Z`.

Refuses (exit 1) when the tag is not `v` plus the version in pyproject.toml, or when CHANGELOG.md
has no section for that version, so a release cannot go out with the wrong or an empty changelog.
Cut the section first with `cz changelog --unreleased-version X.Y.Z` (docs/RELEASING.md).
"""

import re
import sys
import tomllib
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
HEADING = re.compile(r"^## (\S+)", re.MULTILINE)


def project_version(pyproject: str) -> str:
    return str(tomllib.loads(pyproject)["project"]["version"])


def section(changelog: str, version: str) -> str | None:
    """The text under `## <version>` (heading included) up to the next `## `, or None."""
    marks = list(HEADING.finditer(changelog))
    for index, mark in enumerate(marks):
        if mark.group(1) == version:
            end = marks[index + 1].start() if index + 1 < len(marks) else len(changelog)
            return changelog[mark.start() : end].strip()
    return None


def notes_for(tag: str, pyproject: str, changelog: str) -> str:
    """The notes text, or a ValueError that says what is wrong."""
    version = tag.removeprefix("v")
    if not tag.startswith("v") or version != project_version(pyproject):
        raise ValueError(f"tag {tag!r} is not v{project_version(pyproject)} (pyproject.toml)")
    found = section(changelog, version)
    if not found or len(found.splitlines()) < 2:
        raise ValueError(f"CHANGELOG.md has no entries under '## {version}'")
    return found


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: release_notes.py vX.Y.Z", file=sys.stderr)
        return 2
    try:
        notes = notes_for(
            argv[1],
            (REPO / "pyproject.toml").read_text(encoding="utf-8"),
            (REPO / "CHANGELOG.md").read_text(encoding="utf-8"),
        )
    except ValueError as exc:
        print(f"release_notes: {exc}", file=sys.stderr)
        return 1
    print(notes)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
