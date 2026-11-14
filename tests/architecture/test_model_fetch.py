"""The model fetch (scripts/fetch_models.py) is the only network path, and it can never install an
unverified file (DECISIONS #62). Its download command is an argument list over HTTPS only."""

import hashlib
from pathlib import Path

import pytest

from fetch_models import (
    MODEL_URL,
    SEPARATION_RECIPE,
    SEPARATION_URL,
    SEPARATION_WEIGHTS,
    download_argv,
    install,
    install_separation,
)
from filmanalyser.core.config import MODEL_MAX_BYTES
from filmanalyser.core.errors import ModelError
from filmanalyser.media.separation import separation_pins
from filmanalyser.media.vad import MANIFEST_NAME, MODEL_NAME

GOOD = b"the model bytes"


def _manifest_dir(tmp_path: Path, data: bytes) -> Path:
    directory = tmp_path / "models"
    directory.mkdir()
    digest = hashlib.sha256(data).hexdigest()
    (directory / MANIFEST_NAME).write_text(f"{digest}  {MODEL_NAME}\n", encoding="utf-8")
    return directory


@pytest.mark.parametrize("url", [MODEL_URL, SEPARATION_URL])
def test_the_download_is_an_argument_list_over_https_only(url: str) -> None:
    argv = download_argv("/usr/bin/curl", url, Path("out.bin"), MODEL_MAX_BYTES)
    assert isinstance(argv, list) and argv[0] == "/usr/bin/curl"
    assert url.startswith("https://")
    assert argv[argv.index("--proto") + 1] == "=https"
    assert argv[argv.index("--proto-redir") + 1] == "=https"
    assert argv[argv.index("--max-filesize") + 1] == str(MODEL_MAX_BYTES)
    assert "--max-time" in argv
    assert argv[argv.index("--") + 1] == url  # the URL comes after the end-of-options mark


def test_the_separation_files_are_the_ones_the_manifest_pins() -> None:
    pins = separation_pins()
    assert set(pins) == {SEPARATION_WEIGHTS, SEPARATION_RECIPE[0]}
    assert hashlib.sha256(SEPARATION_RECIPE[1]).hexdigest() == pins[SEPARATION_RECIPE[0]]
    assert SEPARATION_URL.endswith("/" + SEPARATION_WEIGHTS)


def _separation_pins(weights: bytes) -> dict[str, str]:
    name, recipe = SEPARATION_RECIPE
    return {
        SEPARATION_WEIGHTS: hashlib.sha256(weights).hexdigest(),
        name: hashlib.sha256(recipe).hexdigest(),
    }


def test_a_verified_separation_download_is_installed(tmp_path: Path) -> None:
    staging, target = tmp_path / "staging", tmp_path / "model"
    staging.mkdir()
    (staging / SEPARATION_WEIGHTS).write_bytes(GOOD)
    assert install_separation(staging, target, _separation_pins(GOOD)) == target
    assert (target / SEPARATION_WEIGHTS).read_bytes() == GOOD
    assert (target / SEPARATION_RECIPE[0]).read_bytes() == SEPARATION_RECIPE[1]


def test_a_bad_separation_download_installs_nothing(tmp_path: Path) -> None:
    staging, target = tmp_path / "staging", tmp_path / "model"
    staging.mkdir()
    (staging / SEPARATION_WEIGHTS).write_bytes(b"tampered weights")
    with pytest.raises(ModelError):
        install_separation(staging, target, _separation_pins(GOOD))
    assert not target.exists()


def test_a_verified_download_is_installed(tmp_path: Path) -> None:
    directory = _manifest_dir(tmp_path, GOOD)
    final = install(GOOD, directory)
    assert final == directory / MODEL_NAME
    assert final.read_bytes() == GOOD
    assert not (directory / (MODEL_NAME + ".partial")).exists()  # staging file is renamed away


def test_a_download_that_does_not_match_is_refused_and_nothing_is_written(tmp_path: Path) -> None:
    directory = _manifest_dir(tmp_path, GOOD)
    with pytest.raises(ModelError):
        install(b"a tampered model", directory)
    assert not (directory / MODEL_NAME).exists()


def test_a_bad_download_never_replaces_a_good_model(tmp_path: Path) -> None:
    directory = _manifest_dir(tmp_path, GOOD)
    install(GOOD, directory)
    with pytest.raises(ModelError):
        install(b"a tampered model", directory)
    assert (directory / MODEL_NAME).read_bytes() == GOOD


def test_a_manifest_without_this_model_refuses_the_install(tmp_path: Path) -> None:
    directory = tmp_path / "models"
    directory.mkdir()
    (directory / MANIFEST_NAME).write_text("0" * 64 + "  other.onnx\n", encoding="utf-8")
    with pytest.raises(ModelError):
        install(GOOD, directory)
