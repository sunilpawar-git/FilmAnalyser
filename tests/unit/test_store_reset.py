"""`--fresh` clears a store without touching anything that is not the store's own."""

from pathlib import Path

import pytest

from filmanalyser.storage.files import remove_matching
from filmanalyser.storage.reset import clear_store
from filmanalyser.storage.schema import MANIFEST_NAME, chunk_file_name


def _fill(root: Path) -> None:
    (root / MANIFEST_NAME).write_text("{}")
    for index in range(3):
        (root / chunk_file_name(index)).write_bytes(b"x")
    (root / ".tmp-abc.part").write_bytes(b"x")


def test_clear_store_removes_the_manifest_the_chunks_and_stale_temp_files(tmp_path: Path) -> None:
    _fill(tmp_path)
    assert clear_store(tmp_path) == 5
    assert list(tmp_path.iterdir()) == []


def test_clear_store_leaves_every_other_file_alone(tmp_path: Path) -> None:
    _fill(tmp_path)
    for name in ("report.html", "notes.txt", "chunk_1.parquet", "manifest.json.bak"):
        (tmp_path / name).write_text("keep")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / chunk_file_name(0)).write_bytes(b"keep")
    clear_store(tmp_path)
    kept = sorted(p.name for p in tmp_path.iterdir())
    assert kept == ["chunk_1.parquet", "manifest.json.bak", "notes.txt", "report.html", "sub"]
    assert (tmp_path / "sub" / chunk_file_name(0)).exists()


def test_clear_store_never_follows_a_symlink(tmp_path: Path) -> None:
    outside = tmp_path / "outside.txt"
    outside.write_text("precious")
    root = tmp_path / "store"
    root.mkdir()
    (root / chunk_file_name(0)).symlink_to(outside)
    assert clear_store(root) == 0
    assert outside.read_text() == "precious"
    assert (root / chunk_file_name(0)).is_symlink()


def test_clear_store_on_a_new_folder_creates_it_and_removes_nothing(tmp_path: Path) -> None:
    assert clear_store(tmp_path / "new") == 0
    assert (tmp_path / "new").is_dir()


def test_remove_matching_counts_only_what_it_removed(tmp_path: Path) -> None:
    (tmp_path / "a.x").write_text("1")
    (tmp_path / "b.y").write_text("2")
    assert remove_matching(tmp_path, ("*.x",)) == 1
    assert (tmp_path / "b.y").exists()


@pytest.mark.parametrize("pattern", ["../*", "a/b", "/etc/*"])
def test_remove_matching_refuses_a_pattern_that_leaves_the_folder(
    tmp_path: Path, pattern: str
) -> None:
    with pytest.raises(ValueError, match="pattern"):
        remove_matching(tmp_path, (pattern,))
