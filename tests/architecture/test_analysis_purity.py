"""The analysis layer is pure and deterministic (EXECUTION_PLAN Phase 6 exit criteria): no I/O, no
report imports, no randomness or clock, and every threshold in core/config.py.

The layer test (test_layer_imports.py) already bars analysis/ from report/ and from I/O modules.
This test pins the rest, and that the modules the plan names exist."""

import ast
from pathlib import Path

from tests.architecture._scan import PKG_ROOT, iter_files, make_package, parse

REQUIRED = ("timeline", "pacing", "tension", "act_breaks", "flags")
NONDETERMINISTIC = {"random", "secrets", "time", "datetime", "uuid", "numpy.random"}
BANNED_CALLS = {"open", "print", "input", "eval", "exec", "compile", "__import__"}
# Structure, not thresholds: counting, indexing and the unit of "per minute" live in the code.
# Every other number must be a named constant imported from core/config.py.
ALLOWED_NUMBERS = {0, 1, 2}


def _imports(tree: ast.Module) -> list[tuple[int, str]]:
    found: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.extend((node.lineno, alias.name) for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.append((node.lineno, node.module))
            found.extend((node.lineno, f"{node.module}.{a.name}") for a in node.names)
    return found


def _is_nondeterministic(name: str) -> bool:
    return any(name == bad or name.startswith(bad + ".") for bad in NONDETERMINISTIC)


def _number_lines(tree: ast.Module) -> list[tuple[int, object]]:
    return [
        (node.lineno, node.value)
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, int | float)
        and not isinstance(node.value, bool)
        and node.value not in ALLOWED_NUMBERS
    ]


def violations(pkg_root: Path) -> list[str]:
    found: list[str] = []
    for path in iter_files(pkg_root / "analysis", (".py",)):
        tree = parse(path)
        found += [
            f"{path.name}:{line}: nondeterministic import '{name}'"
            for line, name in _imports(tree)
            if _is_nondeterministic(name)
        ]
        found += [
            f"{path.name}:{node.lineno}: call to '{node.func.id}' (I/O)"
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id in BANNED_CALLS
        ]
        found += [
            f"{path.name}:{line}: number {value!r} is a threshold: put it in core/config.py"
            for line, value in _number_lines(tree)
        ]
    return found


def test_the_real_analysis_layer_is_pure_deterministic_and_config_driven() -> None:
    assert violations(PKG_ROOT) == []


def test_every_module_the_plan_names_exists() -> None:
    for name in REQUIRED:
        assert (PKG_ROOT / "analysis" / f"{name}.py").is_file(), name


def test_analysis_modules_never_mention_the_report_layer() -> None:
    for path in iter_files(PKG_ROOT / "analysis", (".py",)):
        assert not any(".report" in name for _, name in _imports(parse(path))), path.name


def test_randomness_is_caught(tmp_path: Path) -> None:
    root = make_package(tmp_path, "analysis/bad.py", "import random\n")
    assert violations(root) == ["bad.py:1: nondeterministic import 'random'"]


def test_numpy_random_is_caught(tmp_path: Path) -> None:
    root = make_package(tmp_path, "analysis/bad.py", "from numpy import random\n")
    assert violations(root) == ["bad.py:1: nondeterministic import 'numpy.random'"]


def test_the_clock_is_caught(tmp_path: Path) -> None:
    root = make_package(tmp_path, "analysis/bad.py", "import time\n")
    assert violations(root) != []


def test_a_call_that_does_io_is_caught(tmp_path: Path) -> None:
    root = make_package(tmp_path, "analysis/bad.py", "def f() -> None:\n    print(1)\n")
    assert violations(root) == ["bad.py:2: call to 'print' (I/O)"]


def test_a_threshold_in_code_is_caught(tmp_path: Path) -> None:
    root = make_package(tmp_path, "analysis/bad.py", "LIMIT = 0.75\n")
    assert violations(root) == ["bad.py:1: number 0.75 is a threshold: put it in core/config.py"]


def test_structural_numbers_are_allowed(tmp_path: Path) -> None:
    root = make_package(tmp_path, "analysis/ok.py", "half = 2 // 2\nfirst = [0][0] + 1\n")
    assert violations(root) == []
