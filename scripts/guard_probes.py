"""Deliberate violations, one per guard. Each must make the build fail for the stated reason."""

import hashlib
import sys
from dataclasses import dataclass

PY = [sys.executable, "-m"]
ARCH = [*PY, "pytest", "--no-cov", "-q", "-p", "no:cacheprovider"]
PROBE = "zz_guard_probe"  # every probe file is named so its own report line contains this


@dataclass(frozen=True)
class Probe:
    name: str
    path: str  # relative to the repo root; the file is created, checked, then removed
    content: str
    command: list[str]
    expect: str  # must appear in the failing output, so a probe cannot "pass" for a wrong reason


def _arch(test_file: str) -> list[str]:
    return [*ARCH, f"tests/architecture/{test_file}"]


def _probe(name: str, where: str, content: str, command: list[str], expect: str = PROBE) -> Probe:
    return Probe(name, f"src/filmanalyser/{where}/{PROBE}.py", content, command, expect)


def _many_branches() -> str:
    body = "".join(f"    if x == {i}:\n        return {i}\n" for i in range(12))
    return f"def f(x: int) -> int:\n{body}    return 0\n"


def _long_function() -> str:
    return "def f() -> None:\n" + "".join(f"    x{i} = {i}\n" for i in range(41))


def _fake_token() -> str:
    """A well-formed but fake GitHub token, built at runtime so no literal lives in the repo."""
    return "ghp_" + hashlib.sha256(b"guard-probe").hexdigest()[:36]


def _uncovered_module() -> str:
    return "".join(f"def f{i}() -> int:\n    return {i}\n" for i in range(150))


def architecture_probes() -> list[Probe]:
    layers, strings, colors = (
        _arch("test_layer_imports.py"),
        _arch("test_no_hardcoded_strings.py"),
        _arch("test_no_hardcoded_colors.py"),
    )
    return [
        _probe("file over 300 lines", "core", "x = 1\n" * 301, _arch("test_file_size.py")),
        _probe("core imports report", "core", "from filmanalyser import report\n", layers),
        _probe("pure core imports os", "core", "import os\n", layers),
        _probe("view imports analysis", "report", "from filmanalyser import analysis\n", layers),
        _probe("literal string in cli", "cli", "print('Hello world')\n", strings),
        _probe("hex colour in report", "report", "RED = '#ff0000'\n", colors),
        _probe(
            "mutable dataclass", "core", _mutable_dataclass(), _arch("test_frozen_dataclasses.py")
        ),
        _probe(
            "function over 40 lines", "core", _long_function(), _arch("test_function_limits.py")
        ),
    ]


def security_probes() -> list[Probe]:
    sec = _arch("test_security_patterns.py")
    shell = "import subprocess\nsubprocess.run('ls', shell=True)\n"
    return [
        _probe("shell=True in media", "media", shell, sec),
        _probe("pickle import", "media", "import pickle\n", sec),
        _probe("eval call", "core", "eval('1')\n", sec),
        _probe("network import", "core", "import requests\n", sec),
        _probe("subprocess outside media", "core", "import subprocess\n", sec),
        _probe("security suppression comment", "core", "x = 1  # nosec\n", sec),
        _probe("bandit: shell=True", "media", shell, [*PY, "bandit", "-q", "-r", "src"], "B602"),
    ]


def quality_probes() -> list[Probe]:
    ruff = [*PY, "ruff", "check", "--no-cache", "src"]
    many_args = "def f(a: int, b: int, c: int, d: int, e: int, g: int) -> int:\n    return a\n"
    unit = [*PY, "pytest", "-q", "-p", "no:cacheprovider", "tests/unit"]
    return [
        _probe("complexity over 10", "core", _many_branches(), ruff, "C901"),
        _probe("more than 5 arguments", "core", many_args, ruff, "PLR0913"),
        _probe(
            "untyped function (mypy --strict)",
            "core",
            "def f(x):\n    return x\n",
            [*PY, "mypy"],
            "no-untyped-def",
        ),
        _probe("coverage below gate", "core", _uncovered_module(), unit, "Required test coverage"),
    ]


def source_probes() -> list[Probe]:
    return [*architecture_probes(), *security_probes(), *quality_probes()]


def _mutable_dataclass() -> str:
    return "from dataclasses import dataclass\n\n\n@dataclass\nclass A:\n    x: int\n"


def other_probes() -> list[Probe]:
    return [
        Probe(
            "template literal text",
            f"src/filmanalyser/report/templates/{PROBE}.html",
            "<h1>Hello</h1>\n",
            _arch("test_no_hardcoded_strings.py"),
            PROBE,
        ),
        Probe(
            "template |safe output",
            f"src/filmanalyser/report/templates/{PROBE}.html",
            "<p>{{ x | safe }}</p>\n",
            _arch("test_security_patterns.py"),
            PROBE,
        ),
        Probe(
            "committed secret (gitleaks)",
            f"{PROBE}.txt",
            f"token = {_fake_token()}\n",
            ["gitleaks", "dir", ".", "--no-banner", "--redact", "-v"],
            PROBE,
        ),
        Probe(
            "vulnerable pin (pip-audit)",
            f".cache/{PROBE}.txt",
            "jinja2==2.4.1\n",
            [*PY, "pip_audit", "--disable-pip", "--no-deps", "-r", f".cache/{PROBE}.txt"],
            "vulnerab",
        ),
        Probe(
            "disallowed licence",
            f".cache/{PROBE}.txt",
            "",
            [*PY, "piplicenses", "--allow-only=Not A Real Licence", "--format=plain"],
            "license",
        ),
    ]
