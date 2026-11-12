"""Model integrity (DECISIONS #62): the vendored Silero model must match its pinned SHA-256
before any byte of it is loaded. Parsing and verification are unit-tested here; the shipped
file is checked against the manifest so a silent change to either one fails the build."""

import hashlib
from pathlib import Path

import pytest

from filmanalyser.core.errors import ModelError
from filmanalyser.media import vad
from filmanalyser.media.vad import (
    MANIFEST_NAME,
    MODEL_NAME,
    VoiceDetector,
    model_dir,
    parse_manifest,
    read_verified,
    verify_bytes,
)

PINNED = "1a153a22f4509e292a94e67d6f9b85e8deb25b4988682b7e174c65279d8788e3"  # Silero VAD v6.2.3
DATA = b"model bytes"


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _install(directory: Path, data: bytes = DATA, digest: str | None = None) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / MODEL_NAME).write_bytes(data)
    (directory / MANIFEST_NAME).write_text(
        f"{digest or _sha(DATA)}  {MODEL_NAME}\n", encoding="utf-8"
    )
    return directory


def test_manifest_lines_map_file_names_to_hashes() -> None:
    text = f"{PINNED}  {MODEL_NAME}\n"
    assert parse_manifest(text) == {MODEL_NAME: PINNED}


def test_blank_lines_are_ignored_and_names_may_repeat_only_as_errors() -> None:
    assert parse_manifest(f"\n{PINNED}  {MODEL_NAME}\n\n") == {MODEL_NAME: PINNED}
    with pytest.raises(ModelError):
        parse_manifest(f"{PINNED}  {MODEL_NAME}\n{PINNED}  {MODEL_NAME}\n")


@pytest.mark.parametrize(
    "line",
    [
        "not-a-hash  silero_vad.onnx",  # not 64 hex digits
        PINNED.upper() + "  " + MODEL_NAME,  # hashes are lower-case hex
        PINNED,  # no file name
        f"{PINNED}  ../escape.onnx",  # names must be plain file names
        f"{PINNED}  sub/{MODEL_NAME}",
    ],
)
def test_malformed_manifest_lines_are_refused(line: str) -> None:
    with pytest.raises(ModelError):
        parse_manifest(line + "\n")


def test_matching_bytes_pass_verification() -> None:
    verify_bytes(DATA, _sha(DATA))


def test_a_single_changed_byte_fails_verification() -> None:
    with pytest.raises(ModelError):
        verify_bytes(b"model bytez", _sha(DATA))


def test_read_verified_returns_the_bytes_of_a_matching_model(tmp_path: Path) -> None:
    assert read_verified(_install(tmp_path / "models")) == DATA


def test_read_verified_refuses_a_tampered_model(tmp_path: Path) -> None:
    directory = _install(tmp_path / "models")
    (directory / MODEL_NAME).write_bytes(b"malicious payload")
    with pytest.raises(ModelError) as info:
        read_verified(directory)
    assert info.value.key == "error.model.default"


def test_read_verified_refuses_a_model_the_manifest_does_not_pin(tmp_path: Path) -> None:
    directory = _install(tmp_path / "models", digest="0" * 64)
    with pytest.raises(ModelError):
        read_verified(directory)


def test_read_verified_refuses_a_missing_model_or_manifest(tmp_path: Path) -> None:
    directory = _install(tmp_path / "models")
    (directory / MANIFEST_NAME).unlink()
    with pytest.raises(ModelError):
        read_verified(directory)
    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(ModelError):
        read_verified(empty)


def test_read_verified_refuses_a_manifest_without_this_model(tmp_path: Path) -> None:
    directory = _install(tmp_path / "models")
    (directory / MANIFEST_NAME).write_text(f"{PINNED}  other.onnx\n", encoding="utf-8")
    with pytest.raises(ModelError):
        read_verified(directory)


def test_the_shipped_model_matches_its_pinned_manifest() -> None:
    shipped = read_verified(model_dir())  # raises if the file or the manifest disagree
    assert _sha(shipped) == PINNED


def test_a_model_larger_than_the_bound_is_refused_before_it_is_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    directory = _install(tmp_path / "models")
    monkeypatch.setattr(vad, "MODEL_MAX_BYTES", 4)  # the installed model is longer than 4 bytes
    with pytest.raises(ModelError):
        read_verified(directory)


def test_bytes_that_are_not_an_onnx_model_are_refused(tmp_path: Path) -> None:
    with pytest.raises(ModelError) as info:
        VoiceDetector(b"not an onnx model")
    assert info.value.key == "error.model.default"
