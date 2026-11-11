"""MVVM layering and pure-core rules, enforced on imports (including relative and nested ones)."""

from pathlib import Path

from tests.architecture._scan import (
    PKG_ROOT,
    imported_modules,
    layer_of,
    make_package,
    module_of,
    parse,
)

# Allowed internal dependencies per layer (SSOT for the dependency direction).
# Model = core/storage/analysis; ViewModel = report.viewmodel; View = rest of report + cli.
ALLOWED: dict[str, set[str]] = {
    "core": set(),
    "analysis": {"core"},
    "storage": {"core"},
    "media": {"core"},
    "extractors": {"core"},
    "pipeline": {"core", "media", "storage", "extractors", "analysis"},
    "report": {"core", "analysis"},
    "cli": {"core", "pipeline", "report", "storage"},
}
# Within report/, only the view model may touch analysis; views (renderer, charts) may not.
VIEWMODEL = "filmanalyser.report.viewmodel"
# Pure layers: immutable data in, immutable data out. No I/O, no process or platform access.
PURE_PREFIXES = ("filmanalyser.core", "filmanalyser.analysis", VIEWMODEL)
BANNED_IN_PURE = {"subprocess", "pathlib", "os", "sys", "shutil", "tempfile", "socket", "io"}


def _is_pure(module: str) -> bool:
    return any(module == p or module.startswith(p + ".") for p in PURE_PREFIXES)


def _layer_violations(module: str, target: str) -> str | None:
    own, other = layer_of(module), layer_of(target)
    if not other or other == own:
        return None
    if other not in ALLOWED.get(own, set()):
        return f"layer '{own}' may not import layer '{other}'"
    if own == "report" and other == "analysis" and not module.startswith(VIEWMODEL):
        return "only report.viewmodel may import analysis (views must not)"
    return None


def _pure_violation(module: str, target: str) -> str | None:
    if _is_pure(module) and target.split(".", maxsplit=1)[0] in BANNED_IN_PURE:
        return f"pure module may not import '{target}'"
    return None


def violations(pkg_root: Path) -> list[str]:
    found: list[str] = []
    for path in sorted(pkg_root.rglob("*.py")):
        module = module_of(path, pkg_root)
        tree = parse(path)
        seen: set[int] = set()  # one report per import statement
        for line, target in imported_modules(tree, module, path.name == "__init__.py"):
            reason = _layer_violations(module, target) or _pure_violation(module, target)
            if reason and line not in seen:
                seen.add(line)
                found.append(f"{module}:{line}: {reason}")
    return found


def test_real_tree_respects_layering() -> None:
    assert violations(PKG_ROOT) == []


def test_core_may_not_import_report(tmp_path: Path) -> None:
    root = make_package(tmp_path, "core/bad.py", "from filmanalyser.report import resources\n")
    assert violations(root) == [
        "filmanalyser.core.bad:1: layer 'core' may not import layer 'report'"
    ]


def test_relative_import_is_resolved(tmp_path: Path) -> None:
    root = make_package(tmp_path, "analysis/bad.py", "from ..report import resources\n")
    assert violations(root) == [
        "filmanalyser.analysis.bad:1: layer 'analysis' may not import layer 'report'"
    ]


def test_nested_import_is_caught(tmp_path: Path) -> None:
    root = make_package(tmp_path, "core/bad.py", "def f() -> None:\n    import filmanalyser.cli\n")
    assert "layer 'cli'" in violations(root)[0]


def test_analysis_may_not_import_report(tmp_path: Path) -> None:
    root = make_package(tmp_path, "analysis/bad.py", "import filmanalyser.report.viewmodel\n")
    assert violations(root) != []


def test_views_may_not_import_analysis(tmp_path: Path) -> None:
    root = make_package(tmp_path, "report/renderer.py", "from filmanalyser.analysis import x\n")
    assert "views must not" in violations(root)[0]


def test_viewmodel_may_import_analysis(tmp_path: Path) -> None:
    root = make_package(tmp_path, "report/viewmodel.py", "from filmanalyser.analysis import x\n")
    assert violations(root) == []


def test_cli_may_not_import_analysis(tmp_path: Path) -> None:
    root = make_package(tmp_path, "cli/main.py", "from filmanalyser.analysis import x\n")
    assert violations(root) != []


def test_extractors_may_only_depend_on_core(tmp_path: Path) -> None:
    root = make_package(tmp_path, "extractors/x.py", "from filmanalyser.media import chunker\n")
    assert violations(root) != []


def test_pure_core_may_not_import_io_modules(tmp_path: Path) -> None:
    for name in ("subprocess", "pathlib", "os", "sys"):
        root = make_package(tmp_path, "core/io_bad.py", f"import {name}\n")
        assert violations(root) == [
            f"filmanalyser.core.io_bad:1: pure module may not import '{name}'"
        ]


def test_pure_analysis_and_viewmodel_may_not_import_io(tmp_path: Path) -> None:
    root = make_package(tmp_path, "analysis/a.py", "from pathlib import Path\n")
    root = make_package(tmp_path, "report/viewmodel.py", "import os\n")
    assert len(violations(root)) == 2


def test_io_shell_layers_may_import_io(tmp_path: Path) -> None:
    root = make_package(tmp_path, "media/ok.py", "import subprocess\nimport os\n")
    assert violations(root) == []
