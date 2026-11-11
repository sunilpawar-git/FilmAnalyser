"""Shared helpers for the architecture guards. Checkers take a root so they can be tested
against synthetic violating trees as well as the real source tree."""

import ast
from collections.abc import Iterator
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PKG_ROOT = REPO / "src" / "filmanalyser"
SCRIPTS = REPO / "scripts"
PKG = "filmanalyser"

_SKIP_DIRS = {"__pycache__", ".venv", ".git", ".mypy_cache", ".ruff_cache", ".pytest_cache"}


def iter_files(root: Path, suffixes: tuple[str, ...]) -> Iterator[Path]:
    """Yield files under root with one of the suffixes, in a stable order."""
    for path in sorted(root.rglob("*")):
        if path.is_file() and path.suffix in suffixes and not _SKIP_DIRS & set(path.parts):
            yield path


def parse(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def module_of(path: Path, pkg_root: Path) -> str:
    """Dotted module name of a file inside the package rooted at pkg_root."""
    parts = list(path.relative_to(pkg_root).with_suffix("").parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join([pkg_root.name, *parts])


def layer_of(module: str) -> str:
    """'filmanalyser.core.config' -> 'core'; the package root and non-package names -> ''."""
    parts = module.split(".")
    return parts[1] if len(parts) > 1 and parts[0] == PKG else ""


def imported_modules(tree: ast.Module, module: str, is_package: bool) -> list[tuple[int, str]]:
    """(line, absolute dotted name) for every import in the tree, relative imports resolved."""
    found: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.extend((node.lineno, alias.name) for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            base = _resolve(node, module, is_package)
            found.append((node.lineno, base))
            found.extend((node.lineno, f"{base}.{alias.name}") for alias in node.names)
    return found


def _resolve(node: ast.ImportFrom, module: str, is_package: bool) -> str:
    if node.level == 0:
        return node.module or ""
    anchor = module.split(".")
    drop = node.level - 1 if is_package else node.level
    anchor = anchor[: len(anchor) - drop] if drop else anchor
    return ".".join([*anchor, *([node.module] if node.module else [])])


def make_package(base: Path, rel: str, text: str) -> Path:
    """Write `text` to <base>/filmanalyser/<rel> (creating parents); return the package root."""
    root = base / PKG
    target = root / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
    return root
