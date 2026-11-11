"""Every byte storage/ puts on disk goes through `storage/files.py` (confinement + atomic
temp-file-and-rename). Anywhere else in storage/, a direct write would bypass both."""

import ast
from pathlib import Path

from tests.architecture._scan import PKG_ROOT, make_package, parse

HOME = "files.py"  # the one module allowed to touch the file system
BANNED_CALLS = {"open"}
BANNED_ATTRIBUTES = {
    "write_bytes",
    "write_text",
    "rename",
    "mkstemp",
    "NamedTemporaryFile",
    "TemporaryFile",
    "fdopen",
    "touch",
    "mkdir",
    "unlink",
    "copy",
    "copyfile",
    "move",
    "write_to_dataset",
    "write_feather",
}


def violations(pkg_root: Path) -> list[str]:
    found: list[str] = []
    for path in sorted((pkg_root / "storage").rglob("*.py")):
        if path.name == HOME:
            continue
        for node in ast.walk(parse(path)):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", "")
            os_replace = (
                name == "replace"
                and isinstance(func, ast.Attribute)
                and (isinstance(func.value, ast.Name) and func.value.id == "os")
            )
            if name in BANNED_CALLS | BANNED_ATTRIBUTES or os_replace:
                found.append(f"{path.name}:{node.lineno}: direct file-system write '{name}'")
    return found


def test_real_storage_writes_only_through_files_py() -> None:
    assert violations(PKG_ROOT) == []
    assert (PKG_ROOT / "storage" / HOME).is_file(), "the guard's home module moved: update it"


def test_guard_flags_a_direct_write(tmp_path: Path) -> None:
    source = "def f(p):\n    p.write_bytes(b'x')\n    open('x', 'wb')\n"
    root = make_package(tmp_path, "storage/store.py", source)
    assert [v.split(": ", 1)[1] for v in violations(root)] == [
        "direct file-system write 'write_bytes'",
        "direct file-system write 'open'",
    ]


def test_guard_flags_a_bare_rename_and_os_replace(tmp_path: Path) -> None:
    root = make_package(tmp_path, "storage/store.py", "import os\nos.replace('a', 'b')\n")
    assert len(violations(root)) == 1


def test_guard_ignores_str_replace_and_files_py(tmp_path: Path) -> None:
    make_package(tmp_path, "storage/files.py", "open('x', 'wb')\n")
    root = make_package(tmp_path, "storage/store.py", "x = 'a'.replace('a', 'b')\n")
    assert violations(root) == []
