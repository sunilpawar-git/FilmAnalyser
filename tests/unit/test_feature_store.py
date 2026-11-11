"""The Parquet feature store: append-only, versioned, atomic, and honest about damage."""

import io
import json
import logging
from dataclasses import replace
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from filmanalyser.core.errors import StorageError
from filmanalyser.storage.feature_store import FeatureStore
from filmanalyser.storage.files import sha256_bytes
from filmanalyser.storage.manifest import load_manifest, save_manifest
from filmanalyser.storage.schema import chunk_file_name
from tests.fixtures.store import fill, make_key, make_schema, outputs, tamper


def _open(path: Path, *, cuts_version: int = 1, extra_feature: bool = False) -> FeatureStore:
    schema = make_schema(cuts_version=cuts_version, extra_feature=extra_feature)
    return FeatureStore.open(path, schema, make_key(schema))


def _chunk(path: Path, index: int) -> Path:
    return path / chunk_file_name(index)


def _key(caught: pytest.ExceptionInfo[StorageError]) -> str:
    return caught.value.key


# ---------------------------------------------------------------- round trip, append-only
def test_schema_round_trip(tmp_path: Path) -> None:
    store = _open(tmp_path / "s")
    fill(store, 3)
    columns = store.read_columns()
    assert list(columns) == ["chunk_index", "start_s", "end_s", *make_schema().columns]
    assert columns["chunk_index"].tolist() == [0, 1, 2]
    assert columns["start_s"].tolist() == [0.0, 10.0, 20.0]
    assert columns["shot_cuts.cut_count"].tolist() == [0.0, 1.0, 2.0]
    assert columns["color.brightness"].tolist() == pytest.approx([0.0, 0.1, 0.2])


def test_files_are_real_parquet_carrying_the_version(tmp_path: Path) -> None:
    store = _open(tmp_path / "s")
    fill(store, 1)
    table = pq.read_table(_chunk(tmp_path / "s", 0))
    assert table.num_rows == 1
    assert table.schema.metadata[b"filmanalyser.feature_version"].decode() == make_schema().version


def test_an_empty_store_reads_as_no_rows(tmp_path: Path) -> None:
    columns = _open(tmp_path / "s").read_columns()
    assert all(len(v) == 0 for v in columns.values())
    assert "chunk_index" in columns


def test_writes_are_append_only_and_in_order(tmp_path: Path) -> None:
    store = _open(tmp_path / "s")
    fill(store, 2)
    before = _chunk(tmp_path / "s", 1).read_bytes()
    for index in (0, 1, 3):  # rewrite, rewrite, skip ahead
        with pytest.raises(StorageError) as caught:
            store.append(index, 0.0, 10.0, outputs(index))
        assert _key(caught) == "error.storage.out_of_order"
        assert caught.value.fields == {"expected": 2, "got": index}
    assert _chunk(tmp_path / "s", 1).read_bytes() == before  # nothing was overwritten
    assert store.next_chunk == 2


@pytest.mark.parametrize(
    ("start", "end"), [(5.0, 5.0), (6.0, 5.0), (float("nan"), 1.0), (0.0, float("inf"))]
)
def test_chunk_times_must_be_a_forward_finite_interval(
    tmp_path: Path, start: float, end: float
) -> None:
    store = _open(tmp_path / "s")
    with pytest.raises(StorageError) as caught:
        store.append(0, start, end, outputs(0))
    assert _key(caught) == "error.storage.bad_features"
    assert store.next_chunk == 0 and not _chunk(tmp_path / "s", 0).exists()


def test_features_that_do_not_match_the_schema_store_nothing(tmp_path: Path) -> None:
    store = _open(tmp_path / "s")
    with pytest.raises(StorageError):
        store.append(0, 0.0, 10.0, {"shot_cuts": {"cut_count": 1.0}})
    assert not _chunk(tmp_path / "s", 0).exists() and store.next_chunk == 0


# ---------------------------------------------------------------- versioning and keys
def test_reopening_continues_where_it_stopped(tmp_path: Path) -> None:
    fill(_open(tmp_path / "s"), 4)
    again = _open(tmp_path / "s")
    assert (again.next_chunk, again.complete) == (4, False)
    again.append(4, 40.0, 50.0, outputs(4))
    assert again.read_columns()["chunk_index"].tolist() == [0, 1, 2, 3, 4]


def test_a_changed_extractor_version_is_rejected_never_mixed(tmp_path: Path) -> None:
    fill(_open(tmp_path / "s"), 2)
    with pytest.raises(StorageError) as caught:
        _open(tmp_path / "s", cuts_version=2)
    assert _key(caught) == "error.storage.features_mismatch"


def test_a_changed_feature_list_is_rejected(tmp_path: Path) -> None:
    fill(_open(tmp_path / "s"), 1)
    with pytest.raises(StorageError) as caught:
        _open(tmp_path / "s", extra_feature=True)
    assert _key(caught) == "error.storage.features_mismatch"


def test_a_different_film_is_rejected(tmp_path: Path) -> None:
    fill(_open(tmp_path / "s"), 1)
    with pytest.raises(StorageError) as caught:
        FeatureStore.open(tmp_path / "s", make_schema(), make_key(input_hash="e" * 64))
    assert _key(caught) == "error.storage.input_mismatch"


def test_a_chunk_file_from_another_schema_version_is_never_mixed_in(tmp_path: Path) -> None:
    """Even with a matching hash in the manifest, a file written under another schema is refused."""
    fill(_open(tmp_path / "s"), 2)
    other = make_schema(cuts_version=2)
    data = io.BytesIO()
    pq.write_table(
        pa.table({n: [0] if n == "chunk_index" else [0.0] for n in other.arrow_schema().names})
        .cast(other.arrow_schema()),
        data,
    )  # fmt: skip
    _chunk(tmp_path / "s", 1).write_bytes(data.getvalue())
    manifest = load_manifest(tmp_path / "s")
    assert manifest is not None
    forged = manifest.chunks[:1] + (sha256_bytes(data.getvalue()),)
    save_manifest(tmp_path / "s", replace(manifest, chunks=forged))
    with pytest.raises(StorageError) as caught:
        _open(tmp_path / "s").read_columns()
    assert _key(caught) == "error.storage.chunk_corrupt"


# ---------------------------------------------------------------- completion
def test_a_completed_store_is_reported_and_closed_to_appends(tmp_path: Path) -> None:
    store = _open(tmp_path / "s")
    fill(store, 2)
    store.mark_complete()
    assert _open(tmp_path / "s").complete is True
    with pytest.raises(StorageError) as caught:
        store.append(2, 20.0, 30.0, outputs(2))
    assert _key(caught) == "error.storage.already_complete"


# ---------------------------------------------------------------- crash and damage
def test_a_chunk_file_without_a_manifest_entry_is_redone_identically(tmp_path: Path) -> None:
    """Crash between the chunk write and the manifest write: the manifest is the truth."""
    store = _open(tmp_path / "s")
    fill(store, 2)
    orphan = _chunk(tmp_path / "s", 2)
    orphan.write_bytes(b"left behind by a killed run")
    resumed = _open(tmp_path / "s")
    assert resumed.next_chunk == 2
    resumed.append(2, 20.0, 30.0, outputs(2))
    assert resumed.read_columns()["chunk_index"].tolist() == [0, 1, 2]


def test_stale_temp_files_are_cleaned_on_open(tmp_path: Path) -> None:
    fill(_open(tmp_path / "s"), 1)
    (tmp_path / "s" / ".tmp-killed.part").write_bytes(b"half a chunk")
    _open(tmp_path / "s")
    assert not list((tmp_path / "s").glob(".tmp-*"))


@pytest.mark.parametrize("damage", ["flip", "truncate", "delete", "empty"])
def test_a_damaged_chunk_file_is_a_storage_error_on_open(tmp_path: Path, damage: str) -> None:
    fill(_open(tmp_path / "s"), 3)
    target = _chunk(tmp_path / "s", 1)
    if damage == "flip":
        tamper(target)
    elif damage == "truncate":
        target.write_bytes(target.read_bytes()[:40])
    elif damage == "empty":
        target.write_bytes(b"")
    else:
        target.unlink()
    with pytest.raises(StorageError) as caught:
        _open(tmp_path / "s")
    assert _key(caught) == "error.storage.chunk_corrupt"
    assert caught.value.fields == {"name": chunk_file_name(1)}


def test_a_truncated_manifest_is_a_storage_error_on_open(tmp_path: Path) -> None:
    fill(_open(tmp_path / "s"), 2)
    manifest = tmp_path / "s" / "manifest.json"
    manifest.write_bytes(manifest.read_bytes()[:25])
    with pytest.raises(StorageError) as caught:
        _open(tmp_path / "s")
    assert _key(caught) == "error.storage.manifest_corrupt"


def _forge(root: Path, index: int, content: bytes) -> None:
    """Replace chunk `index` with `content` and make the manifest vouch for it."""
    _chunk(root, index).write_bytes(content)
    manifest = load_manifest(root)
    assert manifest is not None
    chunks = list(manifest.chunks)
    chunks[index] = sha256_bytes(content)
    save_manifest(root, replace(manifest, chunks=tuple(chunks)))


def _parquet(table: pa.Table) -> bytes:
    sink = io.BytesIO()
    pq.write_table(table, sink)
    return sink.getvalue()


def test_content_that_is_not_parquet_is_refused_even_with_a_matching_hash(tmp_path: Path) -> None:
    fill(_open(tmp_path / "s"), 2)
    _forge(tmp_path / "s", 1, b"PAR1 not really parquet")
    with pytest.raises(StorageError) as caught:
        _open(tmp_path / "s").read_columns()
    assert _key(caught) == "error.storage.chunk_corrupt"


def test_wrong_shape_parquet_is_refused_before_it_is_decoded(tmp_path: Path) -> None:
    fill(_open(tmp_path / "s"), 2)
    schema = make_schema().arrow_schema()
    two_rows = pa.table({n: [0, 1] if n == "chunk_index" else [0.0, 1.0] for n in schema.names})
    for bad in (two_rows.cast(schema), pa.table({"chunk_index": pa.array([1], pa.int32())})):
        _forge(tmp_path / "s", 1, _parquet(bad))
        with pytest.raises(StorageError) as caught:
            _open(tmp_path / "s").read_columns()
        assert _key(caught) == "error.storage.chunk_corrupt"


def test_a_row_for_the_wrong_chunk_is_refused(tmp_path: Path) -> None:
    fill(_open(tmp_path / "s"), 2)
    _forge(tmp_path / "s", 1, _chunk(tmp_path / "s", 0).read_bytes())  # chunk 0's data as chunk 1
    with pytest.raises(StorageError) as caught:
        _open(tmp_path / "s").read_columns()
    assert _key(caught) == "error.storage.chunk_corrupt"


def test_a_symlinked_chunk_file_is_refused(tmp_path: Path) -> None:
    fill(_open(tmp_path / "s"), 2)
    outside = tmp_path / "outside.parquet"
    outside.write_bytes(_chunk(tmp_path / "s", 1).read_bytes())
    _chunk(tmp_path / "s", 1).unlink()
    _chunk(tmp_path / "s", 1).symlink_to(outside)
    with pytest.raises(StorageError):
        _open(tmp_path / "s")


# ---------------------------------------------------------------- logging
def test_store_events_are_structured_and_carry_no_paths(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.INFO, logger="filmanalyser"):
        store = _open(tmp_path / "deep" / "store")
        fill(store, 2)
    events = [json.loads(r.getMessage()) for r in caplog.records]
    assert [e["event"] for e in events] == ["store_open", "chunk_stored", "chunk_stored"]
    assert events[0] == {"event": "store_open", "chunks": 0, "complete": False}
    assert events[1]["index"] == 0 and events[1]["bytes"] > 0
    assert str(tmp_path) not in caplog.text
