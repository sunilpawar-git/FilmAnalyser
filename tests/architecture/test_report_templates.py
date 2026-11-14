"""The report is one self-contained page: its templates may carry no script, no external
reference, no inline style or event handler, only defined colour tokens, and the strict CSP."""

import re
from pathlib import Path

from filmanalyser.report.resources.colors import ColorTokens
from tests.architecture._scan import PKG_ROOT, iter_files, make_package

POLICY = "default-src 'none'; style-src 'unsafe-inline'"
BANNED = (
    (re.compile(r"<script|<iframe|<object|<embed|<link\b|<img\b|<form\b", re.I), "active element"),
    (re.compile(r"https?://|//[a-z]", re.I), "external address"),
    (re.compile(r"\b(src|href|action|xlink:href|srcset)\s*=", re.I), "reference attribute"),
    (re.compile(r"\sstyle\s*=", re.I), "inline style attribute"),
    (re.compile(r"\son[a-z]+\s*=", re.I), "event handler"),
    (re.compile(r"url\(|@import|expression\(", re.I), "style reference"),
)
VAR = re.compile(r"var\(--([a-z0-9-]+)\)")
CSP = re.compile(r'http-equiv="Content-Security-Policy"\s+content="([^"]*)"')


def template_problems(root: Path, tokens: set[str]) -> list[str]:
    found: list[str] = []
    for path in iter_files(root / "report" / "templates", (".html",)):
        text = path.read_text(encoding="utf-8")
        found += [f"{path.name}: {what}" for pattern, what in BANNED if pattern.search(text)]
        found += [f"{path.name}: unknown token --{n}" for n in VAR.findall(text) if n not in tokens]
    return found


def csp_policies(root: Path) -> list[str]:
    page = (root / "report" / "templates" / "report.html").read_text(encoding="utf-8")
    return CSP.findall(page)


def test_real_templates_are_self_contained() -> None:
    assert template_problems(PKG_ROOT, set(ColorTokens.load().light)) == []


def test_the_page_carries_the_strict_policy_exactly_once() -> None:
    assert csp_policies(PKG_ROOT) == [POLICY]


def test_guard_flags_a_script(tmp_path: Path) -> None:
    root = make_package(tmp_path, "report/templates/r.html", "<script>x()</script>\n")
    assert template_problems(root, set()) == ["r.html: active element"]


def test_guard_flags_external_addresses_and_references(tmp_path: Path) -> None:
    root = make_package(tmp_path, "report/templates/r.html", '<a href="https://x.test/">x</a>\n')
    assert "r.html: external address" in template_problems(root, set())
    assert "r.html: reference attribute" in template_problems(root, set())


def test_guard_flags_inline_style_and_handlers(tmp_path: Path) -> None:
    root = make_package(tmp_path, "report/templates/r.html", '<p style="x" onclick="y">\n')
    assert template_problems(root, set()) == [
        "r.html: inline style attribute",
        "r.html: event handler",
    ]


def test_guard_flags_an_undefined_token(tmp_path: Path) -> None:
    html = "<style>p { color: var(--nope); }</style>\n"
    root = make_package(tmp_path, "report/templates/r.html", html)
    assert template_problems(root, {"text"}) == ["r.html: unknown token --nope"]


def test_guard_flags_style_references(tmp_path: Path) -> None:
    root = make_package(tmp_path, "report/templates/r.html", "<style>@import 'x';</style>\n")
    assert template_problems(root, set()) == ["r.html: style reference"]
