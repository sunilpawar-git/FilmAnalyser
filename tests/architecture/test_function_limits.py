"""Function length <= 40 lines. (Complexity and argument count are enforced by ruff.)"""

import ast
from pathlib import Path

from tests.architecture._scan import PKG_ROOT, SCRIPTS, iter_files, parse

MAX_LINES = 40


def long_functions(root: Path) -> list[str]:
    bad: list[str] = []
    for path in iter_files(root, (".py",)):
        for node in ast.walk(parse(path)):
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                length = (node.end_lineno or node.lineno) - node.lineno + 1
                if length > MAX_LINES:
                    bad.append(f"{path.name}:{node.lineno}: {node.name} is {length} lines")
    return bad


def test_no_function_exceeds_limit() -> None:
    assert long_functions(PKG_ROOT) + long_functions(SCRIPTS) == []


def test_guard_flags_long_function(tmp_path: Path) -> None:
    body = "".join(f"    x{i} = {i}\n" for i in range(MAX_LINES))
    (tmp_path / "m.py").write_text("def f() -> None:\n" + body)
    assert long_functions(tmp_path) == [f"m.py:1: f is {MAX_LINES + 1} lines"]


def test_guard_accepts_function_at_limit(tmp_path: Path) -> None:
    body = "".join(f"    x{i} = {i}\n" for i in range(MAX_LINES - 1))
    (tmp_path / "m.py").write_text("def f() -> None:\n" + body)
    assert long_functions(tmp_path) == []
