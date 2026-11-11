"""Every dataclass in the package is immutable: @dataclass(frozen=True)."""

import ast
from pathlib import Path

from tests.architecture._scan import PKG_ROOT, iter_files, parse


def _is_frozen(decorator: ast.expr) -> bool | None:
    """None when the decorator is not a dataclass, else whether it is frozen."""
    target = decorator.func if isinstance(decorator, ast.Call) else decorator
    name = target.attr if isinstance(target, ast.Attribute) else getattr(target, "id", "")
    if name != "dataclass":
        return None
    if not isinstance(decorator, ast.Call):
        return False
    return any(
        kw.arg == "frozen" and isinstance(kw.value, ast.Constant) and kw.value.value is True
        for kw in decorator.keywords
    )


def mutable_dataclasses(root: Path) -> list[str]:
    bad: list[str] = []
    for path in iter_files(root, (".py",)):
        for node in ast.walk(parse(path)):
            if isinstance(node, ast.ClassDef):
                flags = [_is_frozen(d) for d in node.decorator_list]
                if False in flags:
                    bad.append(f"{path.name}:{node.lineno}: {node.name} is not frozen")
    return bad


def test_all_dataclasses_are_frozen() -> None:
    assert mutable_dataclasses(PKG_ROOT) == []


def test_guard_flags_bare_dataclass(tmp_path: Path) -> None:
    (tmp_path / "m.py").write_text(
        "from dataclasses import dataclass\n@dataclass\nclass A:\n    x: int\n"
    )
    assert mutable_dataclasses(tmp_path) == ["m.py:3: A is not frozen"]


def test_guard_flags_frozen_false(tmp_path: Path) -> None:
    (tmp_path / "m.py").write_text(
        "import dataclasses\n@dataclasses.dataclass(frozen=False)\nclass A:\n    x: int\n"
    )
    assert len(mutable_dataclasses(tmp_path)) == 1


def test_guard_accepts_frozen(tmp_path: Path) -> None:
    (tmp_path / "m.py").write_text(
        "from dataclasses import dataclass\n@dataclass(frozen=True)\nclass A:\n    x: int\n"
    )
    assert mutable_dataclasses(tmp_path) == []
