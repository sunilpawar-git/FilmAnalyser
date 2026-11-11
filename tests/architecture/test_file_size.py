"""Hard limit: no .py/.html/.toml file over 300 lines unless it carries an SRP exception."""

import re
from pathlib import Path

from tests.architecture._scan import REPO, iter_files

LIMIT = 300
SUFFIXES = (".py", ".html", ".toml")
EXCEPTION = re.compile(r"SRP-EXCEPTION:\s*\S.{12,}")  # a reason, not a placeholder
GENERATED = {"uv.lock"}


def _has_exception(lines: list[str]) -> bool:
    return any(EXCEPTION.search(line) for line in lines[:5])


def oversized(root: Path) -> list[str]:
    bad: list[str] = []
    for path in iter_files(root, SUFFIXES):
        lines = path.read_text(encoding="utf-8").splitlines()
        if len(lines) > LIMIT and not _has_exception(lines) and path.name not in GENERATED:
            bad.append(f"{path.relative_to(root)}: {len(lines)} lines")
    return bad


def test_no_source_file_exceeds_limit() -> None:
    roots = [REPO / "src", REPO / "tests", REPO / "scripts"]
    assert [b for root in roots for b in oversized(root)] == []
    assert len((REPO / "pyproject.toml").read_text().splitlines()) <= LIMIT


def test_guard_flags_oversized_file(tmp_path: Path) -> None:
    (tmp_path / "big.py").write_text("x = 1\n" * (LIMIT + 1))
    assert oversized(tmp_path) == ["big.py: 301 lines"]


def test_guard_accepts_file_at_limit(tmp_path: Path) -> None:
    (tmp_path / "ok.py").write_text("x = 1\n" * LIMIT)
    assert oversized(tmp_path) == []


def test_guard_accepts_documented_srp_exception(tmp_path: Path) -> None:
    header = "# SRP-EXCEPTION: lookup table that must stay whole\n"
    (tmp_path / "table.py").write_text(header + "x = 1\n" * LIMIT)
    assert oversized(tmp_path) == []


def test_guard_rejects_exception_without_reason(tmp_path: Path) -> None:
    (tmp_path / "lazy.py").write_text("# SRP-EXCEPTION:\n" + "x = 1\n" * LIMIT)
    assert oversized(tmp_path) == ["lazy.py: 301 lines"]


def test_guard_covers_html_and_toml(tmp_path: Path) -> None:
    (tmp_path / "t.html").write_text("<p></p>\n" * 400)
    (tmp_path / "t.toml").write_text("a = 1\n" * 400)
    assert len(oversized(tmp_path)) == 2
