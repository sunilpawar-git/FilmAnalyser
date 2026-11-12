"""The model is loaded in one place only: onnxruntime and its session constructor appear in
media/vad.py, and nothing else in the package reads a model file (DECISIONS #62). Together with the
manifest check in `read_verified`, this makes "verified before loaded" a structural fact."""

from pathlib import Path

from tests.architecture._scan import PKG_ROOT, module_of

ALLOWED_MODULE = Path("media") / "vad.py"  # relative to the package root
FORBIDDEN_IN_OTHER_FILES = ("onnxruntime", "InferenceSession", "silero_vad.onnx")


def violations(pkg_root: Path) -> list[str]:
    found: list[str] = []
    for path in sorted(pkg_root.rglob("*.py")):
        if path.relative_to(pkg_root) == ALLOWED_MODULE:
            continue
        text = path.read_text(encoding="utf-8")
        for token in FORBIDDEN_IN_OTHER_FILES:
            if token in text:
                found.append(f"{module_of(path, pkg_root)} mentions {token!r}")
    return found


def test_only_the_voice_module_touches_the_model() -> None:
    assert violations(PKG_ROOT) == []


def test_a_module_that_loads_a_model_outside_vad_is_caught(tmp_path: Path) -> None:
    package = tmp_path / "filmanalyser"
    (package / "pipeline").mkdir(parents=True)
    (package / "media").mkdir()
    (package / "media" / "vad.py").write_text("import onnxruntime\n", encoding="utf-8")
    bad = package / "pipeline" / "runner.py"
    bad.write_text("session = onnxruntime.InferenceSession('x')\n", encoding="utf-8")
    assert violations(package) == [
        "filmanalyser.pipeline.runner mentions 'onnxruntime'",
        "filmanalyser.pipeline.runner mentions 'InferenceSession'",
    ]
