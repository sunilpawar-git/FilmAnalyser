"""File-system safety for the store: confinement, atomic writes, bounded reads, stale temp files."""

import os
from pathlib import Path

import pytest

from filmanalyser.core.errors import InputError, StorageError
from filmanalyser.storage import files
from filmanalyser.storage.files import (
    confined_file,
    open_directory,
    read_bounded,
    remove_stale_temp,
    sha256_bytes,
    sha256_file,
    write_atomic,
)


def _key(caught: pytest.ExceptionInfo[StorageError]) -> str:
    return caught.value.key


# ---------------------------------------------------------------- the chosen directory
def test_open_directory_creates_and_resolves(tmp_path: Path) -> None:
    root = open_directory(tmp_path / "a" / "b")
    assert root == (tmp_path / "a" / "b").resolve()
    assert root.is_dir()


@pytest.mark.parametrize("raw", ["", "   ", "bad\x00name"])
def test_open_directory_rejects_empty_and_nul_paths(raw: str) -> None:
    with pytest.raises(StorageError) as caught:
        open_directory(raw)
    assert _key(caught) == "error.storage.bad_directory"


def test_open_directory_rejects_a_file(tmp_path: Path) -> None:
    (tmp_path / "f").write_text("x")
    with pytest.raises(StorageError) as caught:
        open_directory(tmp_path / "f")
    assert _key(caught) == "error.storage.bad_directory"
    assert caught.value.fields == {"name": "f"}  # basename only


def test_error_fields_never_carry_a_full_path(tmp_path: Path) -> None:
    (tmp_path / "f").write_text("x")
    with pytest.raises(StorageError) as caught:
        open_directory(tmp_path / "f" / "inner")
    assert str(tmp_path) not in str(caught.value)


# ---------------------------------------------------------------- confinement
@pytest.mark.parametrize("name", ["../escape", "a/b", "/abs", "..", ".", "", "x\x00y", "a\\b"])
def test_names_must_be_plain(tmp_path: Path, name: str) -> None:
    with pytest.raises(StorageError) as caught:
        confined_file(open_directory(tmp_path), name)
    assert _key(caught) == "error.storage.bad_directory"


def test_a_symlink_in_place_of_a_file_is_refused(tmp_path: Path) -> None:
    outside = tmp_path / "outside.txt"
    outside.write_text("secret")
    root = open_directory(tmp_path / "store")
    (root / "chunk.bin").symlink_to(outside)
    with pytest.raises(StorageError):
        confined_file(root, "chunk.bin")
    with pytest.raises(StorageError):
        write_atomic(root, "chunk.bin", b"overwrite")
    assert outside.read_text() == "secret"  # nothing escaped the store


def test_a_symlinked_store_directory_is_resolved_to_its_real_path(tmp_path: Path) -> None:
    real = tmp_path / "real"
    real.mkdir()
    (tmp_path / "link").symlink_to(real)
    assert open_directory(tmp_path / "link") == real.resolve()


# ---------------------------------------------------------------- atomic writes
def test_write_then_read_round_trips(tmp_path: Path) -> None:
    root = open_directory(tmp_path)
    write_atomic(root, "a.bin", b"hello")
    assert read_bounded(root, "a.bin", 100, "error.storage.chunk_corrupt") == b"hello"
    assert sorted(p.name for p in root.iterdir()) == ["a.bin"]  # no temp file left behind


def test_a_failed_write_keeps_the_old_file_and_leaves_no_temp_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = open_directory(tmp_path)
    write_atomic(root, "a.bin", b"old")

    def boom(*_: object, **__: object) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(os, "replace", boom)
    with pytest.raises(StorageError) as caught:
        write_atomic(root, "a.bin", b"new and longer")
    assert _key(caught) == "error.storage.write_failed"
    assert (root / "a.bin").read_bytes() == b"old"  # readers never see a half-written file
    assert [p.name for p in root.iterdir()] == ["a.bin"]


def test_a_failure_before_any_temp_file_exists_is_still_a_storage_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def refuse(**_: object) -> tuple[int, str]:
        raise PermissionError("read-only")

    monkeypatch.setattr("tempfile.mkstemp", refuse)
    with pytest.raises(StorageError) as caught:
        write_atomic(open_directory(tmp_path), "a.bin", b"x")
    assert _key(caught) == "error.storage.write_failed"


def test_the_new_content_is_complete_before_it_becomes_visible(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """At the moment of the rename the target still holds the old bytes and the temp file the
    full new bytes: that is what makes a crash at any point safe."""
    root = open_directory(tmp_path)
    write_atomic(root, "a.bin", b"old")
    seen: list[tuple[bytes, bytes]] = []
    real_replace = os.replace

    def spy(src: str | Path, dst: str | Path) -> None:
        seen.append((Path(dst).read_bytes(), Path(src).read_bytes()))
        real_replace(src, dst)

    monkeypatch.setattr(os, "replace", spy)
    write_atomic(root, "a.bin", b"brand new")
    assert seen == [(b"old", b"brand new")]


def test_stale_temp_files_from_a_killed_run_are_removed(tmp_path: Path) -> None:
    root = open_directory(tmp_path)
    (root / ".tmp-abc.part").write_bytes(b"half")
    (root / "keep.bin").write_bytes(b"x")
    assert remove_stale_temp(root) == 1
    assert [p.name for p in root.iterdir()] == ["keep.bin"]


# ---------------------------------------------------------------- bounded reads
def test_oversized_files_are_refused_not_loaded(tmp_path: Path) -> None:
    root = open_directory(tmp_path)
    (root / "big.bin").write_bytes(b"x" * 11)
    with pytest.raises(StorageError) as caught:
        read_bounded(root, "big.bin", 10, "error.storage.manifest_corrupt")
    assert _key(caught) == "error.storage.manifest_corrupt"
    assert read_bounded(root, "big.bin", 11, "error.storage.manifest_corrupt") == b"x" * 11


def test_missing_files_use_the_given_error_key(tmp_path: Path) -> None:
    with pytest.raises(StorageError) as caught:
        read_bounded(open_directory(tmp_path), "no.bin", 10, "error.storage.chunk_corrupt")
    assert _key(caught) == "error.storage.chunk_corrupt"


# ---------------------------------------------------------------- hashing
def test_sha256_matches_the_known_digest_and_streams_in_blocks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    empty = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    assert sha256_bytes(b"") == empty
    film = tmp_path / "film.mp4"
    film.write_bytes(b"abcdefghij" * 5)
    monkeypatch.setattr(files, "HASH_BLOCK_BYTES", 7)  # many blocks, same digest
    assert sha256_file(film) == sha256_bytes(b"abcdefghij" * 5)


def test_hashing_an_unreadable_input_is_an_input_error(tmp_path: Path) -> None:
    with pytest.raises(InputError) as caught:
        sha256_file(tmp_path / "absent.mp4")
    assert caught.value.fields == {"name": "absent.mp4"}
