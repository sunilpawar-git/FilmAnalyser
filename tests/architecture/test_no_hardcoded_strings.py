"""No user-facing text in cli/ or report/ code, or in templates: everything is a resource lookup."""

import ast
import re
from collections.abc import Iterator
from html.parser import HTMLParser
from pathlib import Path

from filmanalyser.report.resources.strings import Strings
from tests.architecture._scan import PKG_ROOT, iter_files, make_package, parse

SCOPES = ("cli", "report")
EXEMPT_DIRS = {"resources"}  # the loaders themselves name their files and tables
TECHNICAL = {"utf-8", "__main__", "r", "rb", "w", "wb"}  # not user-facing
# Technical tokens are not user-facing: option flags, format specs and log formats, and dotted or
# underscored identifiers (column keys, file and package names, argparse actions). Plain words
# and sentences are still text and must come from strings.toml.
_TECHNICAL_PATTERNS = (
    re.compile(r"^--?[a-z][a-z-]*$"),  # -v, --out, --report
    re.compile(r"^\.\d+[fge]$|^%\(\w+\)s$"),  # '.1f', '%(message)s'
    re.compile(r"^[a-z][a-z0-9]*([._][a-z0-9]+)+$"),  # start_s, shot_cuts.cuts, report.html
)
LABEL_ATTRS = {"alt", "title", "aria-label", "placeholder"}


def _skipped_nodes(tree: ast.Module) -> set[int]:
    """ids of string nodes that are docstrings or type annotations (never user-facing)."""
    skip: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
            first = node.body[0] if node.body else None
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant):
                skip.add(id(first.value))
        for ann in _annotations(node):
            skip.update(id(n) for n in ast.walk(ann))
    return skip


def _annotations(node: ast.AST) -> Iterator[ast.expr]:
    found: list[ast.expr | None] = []
    if isinstance(node, ast.AnnAssign | ast.arg):
        found.append(node.annotation)
    elif isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
        found.append(node.returns)
    yield from (ann for ann in found if ann is not None)


def _technical(text: str) -> bool:
    return any(pattern.match(text) for pattern in _TECHNICAL_PATTERNS)


def literal_violations(path: Path, keys: frozenset[str]) -> list[str]:
    tree = parse(path)
    skip = _skipped_nodes(tree)
    bad: list[str] = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Constant) and isinstance(node.value, str)):
            continue
        text = node.value
        if id(node) in skip or text in TECHNICAL or text in keys or _technical(text):
            continue
        if any(ch.isalpha() for ch in text):
            bad.append(f"{path.name}:{node.lineno}: literal {text!r}")
    return bad


class _TemplateText(HTMLParser):
    """Collects visible text and label attributes that are not template expressions."""

    def __init__(self) -> None:
        super().__init__()
        self.found: list[str] = []
        self._muted = 0  # inside <style>/<script>: not visible text

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._muted += tag in {"style", "script"}
        for name, value in attrs:
            if name in LABEL_ATTRS and value and not value.strip().startswith("{{"):
                self.found.append(f"{name}={value!r}")

    def handle_endtag(self, tag: str) -> None:
        self._muted -= tag in {"style", "script"}

    def handle_data(self, data: str) -> None:
        text = _strip_expressions(data).strip()
        if text and not self._muted:
            self.found.append(text)


def _strip_expressions(data: str) -> str:
    for opener, closer in (("{{", "}}"), ("{%", "%}"), ("{#", "#}")):
        while opener in data and closer in data:
            start = data.index(opener)
            data = data[:start] + data[data.index(closer, start) + 2 :]
    return data


def template_violations(path: Path) -> list[str]:
    parser = _TemplateText()
    parser.feed(path.read_text(encoding="utf-8"))
    return [f"{path.name}: literal text {text!r}" for text in parser.found]


def scan(pkg_root: Path, keys: frozenset[str]) -> list[str]:
    bad: list[str] = []
    for scope in SCOPES:
        for path in iter_files(pkg_root / scope, (".py",)):
            if not EXEMPT_DIRS & set(path.relative_to(pkg_root).parts):
                bad.extend(literal_violations(path, keys))
    for path in iter_files(pkg_root / "report", (".html",)):
        bad.extend(template_violations(path))
    return bad


def test_real_tree_has_no_hardcoded_strings() -> None:
    assert scan(PKG_ROOT, Strings.load().keys()) == []


def test_guard_flags_literal_in_cli(tmp_path: Path) -> None:
    root = make_package(tmp_path, "cli/m.py", 'print("Hello there")\n')
    assert scan(root, frozenset()) == ["m.py:1: literal 'Hello there'"]


def test_guard_flags_literal_in_report(tmp_path: Path) -> None:
    root = make_package(tmp_path, "report/m.py", 'TITLE = "Film report"\n')
    assert len(scan(root, frozenset())) == 1


def test_guard_flags_fstring_text(tmp_path: Path) -> None:
    root = make_package(tmp_path, "cli/m.py", 'x = 1\nprint(f"Found {x} cuts")\n')
    assert len(scan(root, frozenset())) == 2  # both literal parts of the f-string


def test_guard_allows_docstrings_annotations_and_keys(tmp_path: Path) -> None:
    source = '"""Doc."""\nfrom typing import Literal\nx: Literal["a", "b"]\ny = t("app.name")\n'
    root = make_package(tmp_path, "cli/m.py", source)
    assert scan(root, frozenset({"app.name"})) == []


def test_guard_allows_separators(tmp_path: Path) -> None:
    root = make_package(tmp_path, "cli/m.py", 'x = ", ".join([])\ny = "\\n" + "-" * 3\n')
    assert scan(root, frozenset()) == []


def test_guard_ignores_other_layers_and_resources(tmp_path: Path) -> None:
    root = make_package(tmp_path, "core/m.py", 'x = "plain words"\n')
    make_package(tmp_path, "report/resources/m.py", 'x = "strings.toml"\n')
    assert scan(root, frozenset()) == []


def test_guard_flags_literal_template_text(tmp_path: Path) -> None:
    root = make_package(tmp_path, "report/templates/r.html", "<h1>Film report</h1>\n")
    assert scan(root, frozenset()) == ["r.html: literal text 'Film report'"]


def test_guard_flags_literal_alt_text(tmp_path: Path) -> None:
    root = make_package(tmp_path, "report/templates/r.html", '<img alt="A chart">\n')
    assert len(scan(root, frozenset())) == 1


def test_guard_allows_expressions_and_style(tmp_path: Path) -> None:
    html = '<style>p { color: var(--text); }</style><h1>{{ t.title }}</h1><img alt="{{ t.alt }}">\n'
    root = make_package(tmp_path, "report/templates/r.html", html)
    assert scan(root, frozenset()) == []
