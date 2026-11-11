"""Every error raised with a message key must name a real entry in strings.toml, so no error
reaches a user without a (non-hardcoded) message."""

import ast
from pathlib import Path

from filmanalyser.core.errors import ERROR_TAXONOMY
from filmanalyser.report.resources.strings import Strings
from tests.architecture._scan import PKG_ROOT, iter_files, make_package, parse


def key_literals(pkg_root: Path) -> list[tuple[str, int, str]]:
    """(file, line, value) for every `key="..."` keyword argument in the package."""
    found: list[tuple[str, int, str]] = []
    for path in iter_files(pkg_root, (".py",)):
        for node in ast.walk(parse(path)):
            if isinstance(node, ast.Call):
                found.extend(
                    (path.name, node.lineno, kw.value.value)
                    for kw in node.keywords
                    if kw.arg == "key"
                    and isinstance(kw.value, ast.Constant)
                    and isinstance(kw.value.value, str)
                )
    return found


def unknown_keys(pkg_root: Path, known: frozenset[str]) -> list[str]:
    return [
        f"{f}:{n}: unknown message key {k!r}"
        for f, n, k in key_literals(pkg_root)
        if k not in known
    ]


def test_every_category_message_key_exists() -> None:
    known = Strings.load().keys()
    assert {cls.message_key for cls in ERROR_TAXONOMY} <= known


def test_every_key_used_in_the_source_exists() -> None:
    assert key_literals(PKG_ROOT), "the guard found no error keys at all: it is not looking"
    assert unknown_keys(PKG_ROOT, Strings.load().keys()) == []


def test_guard_flags_an_unknown_key(tmp_path: Path) -> None:
    root = make_package(tmp_path, "media/m.py", "raise InputError(key='error.input.made_up')\n")
    assert unknown_keys(root, frozenset({"error.input.default"})) == [
        "m.py:1: unknown message key 'error.input.made_up'"
    ]


def test_guard_accepts_a_known_key(tmp_path: Path) -> None:
    root = make_package(tmp_path, "media/m.py", "raise InputError(key='error.input.default')\n")
    assert unknown_keys(root, frozenset({"error.input.default"})) == []
