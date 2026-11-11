"""Every subprocess call in media/ takes its command from a `*_argv` builder, so the command
line is constructed in one tested place (list form, validated path, `--` / file: protection)."""

import ast
from pathlib import Path

from tests.architecture._scan import PKG_ROOT, make_package, parse

SPAWNERS = {"run", "Popen", "check_output", "check_call", "call"}


def _is_argv_source(node: ast.expr) -> bool:
    if isinstance(node, ast.Name):
        return node.id == "argv" or node.id.endswith("_argv")
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
        return node.func.id.endswith("_argv")
    return False


def _is_spawn(node: ast.Call) -> bool:
    func = node.func
    return (
        isinstance(func, ast.Attribute)
        and func.attr in SPAWNERS
        and isinstance(func.value, ast.Name)
        and func.value.id == "subprocess"
    )


def violations(pkg_root: Path) -> list[str]:
    found: list[str] = []
    for path in sorted((pkg_root / "media").rglob("*.py")):
        for node in ast.walk(parse(path)):
            if isinstance(node, ast.Call) and _is_spawn(node):
                first = node.args[0] if node.args else None
                if first is None or not _is_argv_source(first):
                    found.append(
                        f"{path.name}:{node.lineno}: subprocess call without an argv builder"
                    )
    return found


def test_real_tree_builds_every_command_through_an_argv_builder() -> None:
    assert violations(PKG_ROOT) == []
    spawns = [
        n
        for p in (PKG_ROOT / "media").rglob("*.py")
        for n in ast.walk(parse(p))
        if isinstance(n, ast.Call) and _is_spawn(n)
    ]
    assert spawns, "the guard found no subprocess calls: it is not looking"


def test_guard_flags_an_inline_command_list(tmp_path: Path) -> None:
    source = "import subprocess\nsubprocess.run(['ffmpeg', '-i', user_path])\n"
    root = make_package(tmp_path, "media/m.py", source)
    assert violations(root) == ["m.py:2: subprocess call without an argv builder"]


def test_guard_flags_an_fstring_command(tmp_path: Path) -> None:
    root = make_package(tmp_path, "media/m.py", "import subprocess\nsubprocess.Popen(f'x {p}')\n")
    assert len(violations(root)) == 1


def test_guard_accepts_argv_builders(tmp_path: Path) -> None:
    source = (
        "import subprocess\n"
        "subprocess.run(probe_argv(a, b))\n"
        "argv = decode_argv(a)\n"
        "subprocess.Popen(argv)\n"
    )
    assert violations(make_package(tmp_path, "media/m.py", source)) == []


def test_guard_only_looks_at_media(tmp_path: Path) -> None:
    root = make_package(tmp_path, "core/m.py", "import subprocess\nsubprocess.run(['x'])\n")
    assert violations(root) == []
