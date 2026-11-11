"""The resume manifest: what is finished, for which film, features and settings."""

import json
from pathlib import Path

import pytest

from filmanalyser.core.errors import StorageError
from filmanalyser.storage.files import open_directory, write_atomic
from filmanalyser.storage.manifest import Manifest, RunKey, load_manifest, save_manifest
from tests.fixtures.store import CONFIG, INPUT_HASH, make_key, make_schema

DIGEST = "b" * 64


def _fresh() -> Manifest:
    return Manifest(make_key())


def test_a_new_manifest_has_nothing_finished() -> None:
    manifest = _fresh()
    assert (manifest.finished, manifest.complete) == (0, False)


def test_chunks_are_recorded_in_order_and_the_original_is_untouched() -> None:
    first = _fresh()
    second = first.with_chunk(DIGEST).with_chunk("c" * 64)
    assert (first.finished, second.finished) == (0, 2)
    assert second.chunks == (DIGEST, "c" * 64)
    assert second.completed().complete is True


def test_round_trip_through_disk(tmp_path: Path) -> None:
    root = open_directory(tmp_path)
    manifest = _fresh().with_chunk(DIGEST).completed()
    save_manifest(root, manifest)
    assert load_manifest(root) == manifest


def test_no_manifest_is_none_not_an_error(tmp_path: Path) -> None:
    assert load_manifest(open_directory(tmp_path)) is None


def test_serialisation_is_canonical_and_has_no_timestamps() -> None:
    first, second = _fresh().with_chunk(DIGEST), _fresh().with_chunk(DIGEST)
    assert first.to_bytes() == second.to_bytes()
    assert set(json.loads(first.to_bytes())) == {
        "format",
        "input_hash",
        "feature_version",
        "geometry",
        "complete",
        "chunks",
    }


_GOOD = json.loads(_fresh().with_chunk(DIGEST).to_bytes())


def _with(**changes: object) -> bytes:
    return json.dumps({**_GOOD, **changes}).encode()


@pytest.mark.parametrize(
    "content",
    [
        b"",  # empty (crash before the first write completed)
        b'{"format": 1, "input_h',  # truncated
        b"\xff\xfe\x00garbage",  # not text
        b"[1, 2, 3]",  # not an object
        b"null",
        _with(format=99),  # unknown layout
        _with(format="1"),
        _with(input_hash="short"),
        _with(input_hash="Z" * 64),
        _with(feature_version=5),
        _with(geometry=[]),
        _with(geometry={"chunk_seconds": "ten"}),
        _with(geometry={"chunk_seconds": True}),
        _with(complete="yes"),
        _with(chunks="not a list"),
        _with(chunks=["nothex" + "0" * 58]),
        _with(chunks=[1, 2]),
        json.dumps({k: v for k, v in _GOOD.items() if k != "chunks"}).encode(),
        json.dumps({**_GOOD, "extra": 1}).encode(),  # unknown keys are rejected too
    ],
)
def test_a_corrupt_manifest_is_a_storage_error_not_a_crash(tmp_path: Path, content: bytes) -> None:
    root = open_directory(tmp_path)
    write_atomic(root, "manifest.json", content)
    with pytest.raises(StorageError) as caught:
        load_manifest(root)
    assert caught.value.key == "error.storage.manifest_corrupt"
    assert caught.value.fields == {"name": "manifest.json"}


def test_an_oversized_manifest_is_refused(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = open_directory(tmp_path)
    save_manifest(root, _fresh())
    monkeypatch.setattr("filmanalyser.storage.manifest.STORE_MAX_FILE_BYTES", 10)
    with pytest.raises(StorageError) as caught:
        load_manifest(root)
    assert caught.value.key == "error.storage.manifest_corrupt"


# ---------------------------------------------------------------- keyed by input + version
def test_the_same_key_is_accepted() -> None:
    _fresh().require(make_key(), "store")


@pytest.mark.parametrize(
    ("key", "error"),
    [
        (make_key(input_hash="d" * 64), "error.storage.input_mismatch"),
        (make_key(make_schema(cuts_version=2)), "error.storage.features_mismatch"),
        (
            RunKey(INPUT_HASH, make_schema().version, {**CONFIG.geometry(), "frame_width": 32}),
            "error.storage.settings_mismatch",
        ),
    ],
)
def test_a_different_key_is_rejected_never_mixed(key: RunKey, error: str) -> None:
    with pytest.raises(StorageError) as caught:
        _fresh().require(key, "store")
    assert caught.value.key == error
    assert caught.value.fields == {"name": "store"}
