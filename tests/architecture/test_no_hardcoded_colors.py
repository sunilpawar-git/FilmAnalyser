"""Colours are design tokens in colors.toml only: no hex/rgb/hsl literals anywhere else."""

import ast
import re
from pathlib import Path

from tests.architecture._scan import PKG_ROOT, iter_files, parse

COLOR = re.compile(
    r"#(?:[0-9a-fA-F]{8}|[0-9a-fA-F]{6}|[0-9a-fA-F]{3,4})\b|\b(?:rgb|rgba|hsl|hsla)\s*\(",
)
TEXT_SUFFIXES = (".html", ".css", ".svg", ".toml", ".js")
PALETTE_FILE = "colors.toml"


def _py_colors(path: Path) -> list[str]:
    """Colour literals inside Python string constants (comments are not scanned)."""
    return [
        f"{path.name}:{node.lineno}: {match.group()}"
        for node in ast.walk(parse(path))
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
        for match in COLOR.finditer(node.value)
    ]


def _text_colors(path: Path) -> list[str]:
    lines = path.read_text(encoding="utf-8").splitlines()
    return [
        f"{path.name}:{n}: {match.group()}"
        for n, line in enumerate(lines, 1)
        for match in COLOR.finditer(line)
    ]


def color_literals(root: Path) -> list[str]:
    bad: list[str] = []
    for path in iter_files(root, (".py", *TEXT_SUFFIXES)):
        if path.name == PALETTE_FILE:
            continue
        bad.extend(_py_colors(path) if path.suffix == ".py" else _text_colors(path))
    return bad


def test_real_tree_has_no_color_literals() -> None:
    assert color_literals(PKG_ROOT) == []


def test_tokens_file_is_where_colors_live() -> None:
    assert COLOR.search((PKG_ROOT / "report/resources" / PALETTE_FILE).read_text())


def test_guard_flags_hex_in_python(tmp_path: Path) -> None:
    (tmp_path / "m.py").write_text('RED = "#ff0000"\n')
    assert color_literals(tmp_path) == ["m.py:1: #ff0000"]


def test_guard_flags_short_hex_and_rgb_in_python(tmp_path: Path) -> None:
    (tmp_path / "m.py").write_text('A = "#fff"\nB = "rgb(1, 2, 3)"\nC = "hsla(0, 0%, 0%, 1)"\n')
    assert len(color_literals(tmp_path)) == 3


def test_guard_ignores_python_comments(tmp_path: Path) -> None:
    (tmp_path / "m.py").write_text("# issue #123 and #ff0000 in a comment\nx = 1\n")
    assert color_literals(tmp_path) == []


def test_guard_flags_hex_in_template_and_css(tmp_path: Path) -> None:
    (tmp_path / "r.html").write_text('<p style="color: #123456">x</p>\n')
    (tmp_path / "s.css").write_text("p { background: rgb(0,0,0); }\n")
    assert len(color_literals(tmp_path)) == 2


def test_guard_allows_var_tokens(tmp_path: Path) -> None:
    (tmp_path / "s.css").write_text("p { color: var(--text); }\n")
    assert color_literals(tmp_path) == []


def test_guard_allows_the_token_file(tmp_path: Path) -> None:
    (tmp_path / PALETTE_FILE).write_text('text = "#112233"\n')
    assert color_literals(tmp_path) == []
