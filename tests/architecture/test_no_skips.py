"""No test may skip, xfail or import-skip (EXECUTION_PLAN section 1: "no skips or xfails").
A missing prerequisite must fail the test loudly. Marker deselection is allowed (DECISIONS #53)."""

import ast
from pathlib import Path

from tests.architecture._scan import REPO, iter_files, make_package, parse

TESTS = REPO / "tests"
BANNED = {"skip", "skipif", "xfail", "importorskip"}


def _banned_attr(node: ast.expr) -> str | None:
    """`pytest.skip`, `pytest.mark.skip(...)`, `pytest.mark.skipif`, `pytest.importorskip`, ..."""
    if isinstance(node, ast.Attribute) and node.attr in BANNED:
        base = node.value
        if isinstance(base, ast.Name) and base.id == "pytest":
            return f"pytest.{node.attr}"
        if isinstance(base, ast.Attribute) and base.attr == "mark":
            return f"pytest.mark.{node.attr}"
    return None


def violations(root: Path) -> list[str]:
    found: list[str] = []
    for path in iter_files(root, (".py",)):
        for node in ast.walk(parse(path)):
            if isinstance(node, ast.Attribute) and (name := _banned_attr(node)):
                found.append(f"{path.name}:{node.lineno}: {name}")
            if isinstance(node, ast.Name) and node.id == "importorskip":
                found.append(f"{path.name}:{node.lineno}: importorskip")
    return found


def test_real_tests_never_skip_or_xfail() -> None:
    assert violations(TESTS) == []


def test_guard_flags_skip_marks_and_skip_calls(tmp_path: Path) -> None:
    source = (
        "import pytest\n"
        "@pytest.mark.skipif(True, reason='x')\n"
        "def test_a() -> None:\n"
        "    pytest.skip('no ffmpeg')\n"
        "@pytest.mark.xfail\n"
        "def test_b() -> None:\n"
        "    pytest.importorskip('numpy')\n"
    )
    root = make_package(tmp_path, "m.py", source)
    assert len(violations(root)) == 4
    assert all("skip" in v or "xfail" in v for v in violations(root))


def test_deselecting_a_marker_is_not_flagged(tmp_path: Path) -> None:
    root = make_package(
        tmp_path, "m.py", "import pytest\n@pytest.mark.real_clip\ndef test_a(): ...\n"
    )
    assert violations(root) == []
