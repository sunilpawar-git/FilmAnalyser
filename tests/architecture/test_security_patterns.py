"""Banned security patterns: shell=True, pickle, eval/exec, network access, unsafe HTML output,
and suppression comments that would hide any of those from bandit/ruff."""

import ast
import re
import tokenize
from pathlib import Path

from tests.architecture._scan import (
    PKG_ROOT,
    SCRIPTS,
    iter_files,
    make_package,
    module_of,
    parse,
)

BANNED_IMPORTS = {
    "pickle",
    "cPickle",
    "_pickle",
    "marshal",
    "shelve",
    "dill",
    "cloudpickle",  # deserialisation
    "requests",
    "urllib.request",
    "urllib3",
    "http.client",
    "httpx",
    "aiohttp",
    "socket",
    "ftplib",
    "smtplib",
    "telnetlib",
    "xmlrpc",
    "websockets",
    "webbrowser",  # network access
    "markupsafe",  # Markup() bypasses autoescape
}
BANNED_CALLS = {"eval", "exec", "compile", "__import__", "os.system", "os.popen", "Markup"}
SUBPROCESS_HOMES = {"media"}  # the only package allowed to spawn processes (scripts/ also may)
SUPPRESSION = re.compile(r"#\s*(nosec|noqa:\s*S\d)")
HTML_UNSAFE = re.compile(r"\|\s*safe\b|autoescape\s+false", re.IGNORECASE)


def _dotted(node: ast.expr) -> str:
    if isinstance(node, ast.Attribute):
        return f"{_dotted(node.value)}.{node.attr}"
    return node.id if isinstance(node, ast.Name) else ""


def _import_names(node: ast.AST) -> list[str]:
    if isinstance(node, ast.Import):
        return [alias.name for alias in node.names]
    if isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
        return [node.module, *(f"{node.module}.{alias.name}" for alias in node.names)]
    return []


def _banned_import(name: str) -> bool:
    return any(name == b or name.startswith(b + ".") for b in BANNED_IMPORTS)


def _call_problems(node: ast.Call) -> list[str]:
    problems = []
    if _dotted(node.func) in BANNED_CALLS:
        problems.append(f"call to {_dotted(node.func)}()")
    if any(kw.arg == "shell" and getattr(kw.value, "value", None) is True for kw in node.keywords):
        problems.append("shell=True")
    if any(
        kw.arg == "autoescape" and getattr(kw.value, "value", None) is False for kw in node.keywords
    ):
        problems.append("autoescape=False")
    return problems


def python_problems(path: Path, allow_subprocess: bool) -> list[str]:
    found: list[str] = []
    for node in ast.walk(parse(path)):
        line = getattr(node, "lineno", 0)
        for name in _import_names(node):
            if _banned_import(name):
                found.append(f"{path.name}:{line}: import {name}")
            if name == "subprocess" and not allow_subprocess:
                found.append(f"{path.name}:{line}: subprocess outside media/")
        if isinstance(node, ast.Call):
            found.extend(f"{path.name}:{node.lineno}: {p}" for p in _call_problems(node))
    found.extend(_suppressions(path))
    return found


def _suppressions(path: Path) -> list[str]:
    """Real comments only (strings that merely mention '# nosec' are fine)."""
    with path.open("rb") as handle:
        return [
            f"{path.name}:{token.start[0]}: security suppression comment"
            for token in tokenize.tokenize(handle.readline)
            if token.type == tokenize.COMMENT and SUPPRESSION.search(token.string)
        ]


def scan(pkg_root: Path, scripts: Path | None = None) -> list[str]:
    found: list[str] = []
    for path in iter_files(pkg_root, (".py",)):
        home = module_of(path, pkg_root).split(".")[1:2]
        found.extend(python_problems(path, allow_subprocess=bool(SUBPROCESS_HOMES & set(home))))
    for path in iter_files(scripts, (".py",)) if scripts else []:
        found.extend(python_problems(path, allow_subprocess=True))
    for path in iter_files(pkg_root, (".html",)):
        found.extend(
            f"{path.name}:{n}: unsafe HTML output"
            for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
            if HTML_UNSAFE.search(line)
        )
    return found


def test_real_tree_has_no_banned_patterns() -> None:
    assert scan(PKG_ROOT, SCRIPTS) == []


CORE = "core/m.py"


def test_guard_flags_shell_true(tmp_path: Path) -> None:
    source = "import subprocess\nsubprocess.run('ls', shell=True)\n"
    assert scan(make_package(tmp_path, "media/m.py", source)) == ["m.py:2: shell=True"]


def test_guard_flags_pickle_and_marshal(tmp_path: Path) -> None:
    assert scan(make_package(tmp_path, CORE, "import pickle\n")) == ["m.py:1: import pickle"]
    assert len(scan(make_package(tmp_path, CORE, "from marshal import loads\n"))) == 2


def test_guard_flags_eval_exec_compile(tmp_path: Path) -> None:
    source = "eval('1')\nexec('x=1')\ncompile('1', 'f', 'eval')\n"
    assert len(scan(make_package(tmp_path, CORE, source))) == 3


def test_guard_flags_os_system(tmp_path: Path) -> None:
    root = make_package(tmp_path, CORE, "import os\nos.system('ls')\n")
    assert scan(root) == ["m.py:2: call to os.system()"]


def test_guard_flags_network_modules(tmp_path: Path) -> None:
    for source in (
        "import requests\n",
        "import urllib.request\n",
        "import socket\n",
        "from http import client\nfrom http.client import HTTPConnection\n",
    ):
        assert scan(make_package(tmp_path, CORE, source)) != []


def test_guard_allows_urllib_parse(tmp_path: Path) -> None:
    assert scan(make_package(tmp_path, CORE, "from urllib.parse import quote\n")) == []


def test_guard_confines_subprocess_to_media(tmp_path: Path) -> None:
    outside = make_package(tmp_path / "a", CORE, "import subprocess\n")
    assert scan(outside) == ["m.py:1: subprocess outside media/"]
    assert scan(make_package(tmp_path / "b", "media/m.py", "import subprocess\n")) == []


def test_guard_flags_suppression_comments(tmp_path: Path) -> None:
    source = "x = 1  # nosec\ny = 2  # noqa: S101\n"
    assert len(scan(make_package(tmp_path, CORE, source))) == 2


def test_guard_ignores_suppression_text_inside_strings(tmp_path: Path) -> None:
    assert scan(make_package(tmp_path, CORE, "x = '# nosec'\n")) == []


def test_guard_allows_unrelated_noqa(tmp_path: Path) -> None:
    assert scan(make_package(tmp_path, CORE, "x = 1  # noqa: E501\n")) == []


def test_guard_flags_autoescape_off_and_markup(tmp_path: Path) -> None:
    source = "env = Env(autoescape=False)\nx = Markup('<b>')\n"
    assert len(scan(make_package(tmp_path, "report/m.py", source))) == 2


def test_guard_flags_unsafe_template_output(tmp_path: Path) -> None:
    root = make_package(
        tmp_path, "report/t.html", "<p>{{ x | safe }}</p>\n{% autoescape false %}\n"
    )
    assert len(scan(root)) == 2


def test_guard_scans_scripts_for_shell_true(tmp_path: Path) -> None:
    root = make_package(tmp_path, CORE, "x = 1\n")
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    (scripts / "s.py").write_text("import subprocess\nsubprocess.run('x', shell=True)\n")
    assert scan(root, scripts) == ["s.py:2: shell=True"]
