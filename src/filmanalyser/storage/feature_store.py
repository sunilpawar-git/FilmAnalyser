"""The Parquet feature store: one file per chunk, append-only, atomic, verified on every read.

Layout of an output directory: `manifest.json` plus `chunk_NNNNNN.parquet`, one single-row file
per chunk. Appending a chunk writes its file atomically, then records its sha256 in the manifest
(also atomically), so a crash at any moment leaves a consistent store: the manifest is the truth
and an unlisted file is simply redone. Files are only ever read after their hash matches the
manifest and their shape matches the schema (Parquet through pyarrow only: no pickle, no
pandas, no object columns), so a damaged or swapped file is a StorageError, never silent data.
"""

import io
from collections.abc import Mapping
from pathlib import Path
from typing import Self

import numpy as np
import numpy.typing as npt
import pyarrow as pa
import pyarrow.parquet as pq

from filmanalyser.core.config import STORE_MAX_FILE_BYTES
from filmanalyser.core.errors import StorageError
from filmanalyser.core.events import log_event
from filmanalyser.storage.files import (
    open_directory,
    read_bounded,
    remove_stale_temp,
    sha256_bytes,
    write_atomic,
)
from filmanalyser.storage.manifest import Manifest, RunKey, load_manifest, save_manifest
from filmanalyser.storage.schema import (
    END_COLUMN,
    INDEX_COLUMN,
    META_VERSION,
    START_COLUMN,
    FeatureSchema,
    chunk_file_name,
)

Columns = dict[str, npt.NDArray[np.generic]]
_CORRUPT = "error.storage.chunk_corrupt"


class FeatureStore:
    def __init__(self, root: Path, schema: FeatureSchema, manifest: Manifest) -> None:
        self._root, self._schema, self._manifest = root, schema, manifest

    @classmethod
    def open(cls, directory: str | Path, schema: FeatureSchema, key: RunKey) -> Self:
        """Open (or start) the store in `directory`. A store made for another film, extractor
        versions or chunk settings is rejected; so is any damage to what it already holds."""
        root = open_directory(directory)
        remove_stale_temp(root)
        manifest = load_manifest(root)
        if manifest is None:
            manifest = Manifest(key)
            save_manifest(root, manifest)
        manifest.require(key, root.name)
        store = cls(root, schema, manifest)
        for index in range(manifest.finished):
            store._verified(index)  # fail now, not halfway through the analysis
        log_event("store_open", chunks=manifest.finished, complete=manifest.complete)
        return store

    @property
    def next_chunk(self) -> int:
        """Index of the first chunk not yet stored: where a resumed run starts decoding."""
        return self._manifest.finished

    @property
    def complete(self) -> bool:
        return self._manifest.complete

    def append(
        self, index: int, start_s: float, end_s: float, outputs: Mapping[str, Mapping[str, float]]
    ) -> None:
        """Store one chunk's features. Strictly sequential: results are append-only."""
        if self._manifest.complete:
            raise StorageError(key="error.storage.already_complete", name=self._root.name)
        if index != self.next_chunk:
            raise StorageError(
                key="error.storage.out_of_order", expected=self.next_chunk, got=index
            )
        data = self._encode(index, start_s, end_s, self._schema.row(outputs))
        write_atomic(self._root, chunk_file_name(index), data)
        updated = self._manifest.with_chunk(sha256_bytes(data))
        save_manifest(self._root, updated)  # only now is the chunk "finished"
        self._manifest = updated
        log_event("chunk_stored", index=index, bytes=len(data))

    def mark_complete(self) -> None:
        updated = self._manifest.completed()
        save_manifest(self._root, updated)
        self._manifest = updated

    def read_columns(self) -> Columns:
        """Every stored chunk as one array per column (chunk_index, times, then the features)."""
        tables = [self._table(i) for i in range(self._manifest.finished)]
        names = self._schema.arrow_schema().names
        if not tables:
            return {n: np.empty(0) for n in names}
        whole = pa.concat_tables(tables)
        return {n: whole.column(n).to_numpy() for n in names}

    # ------------------------------------------------------------------ internals
    def _encode(self, index: int, start_s: float, end_s: float, row: dict[str, float]) -> bytes:
        if not 0 <= start_s < end_s or end_s == float("inf"):
            raise StorageError(key="error.storage.bad_features", name=END_COLUMN)
        schema = self._schema.arrow_schema()
        values = {INDEX_COLUMN: [index], START_COLUMN: [start_s], END_COLUMN: [end_s]}
        values.update({name: [value] for name, value in row.items()})
        sink = io.BytesIO()
        # Fixed options and no pandas/created-at metadata: equal input gives equal bytes.
        pq.write_table(
            pa.table(values, schema=schema), sink, compression="zstd", use_dictionary=False
        )
        return sink.getvalue()

    def _verified(self, index: int) -> bytes:
        name = chunk_file_name(index)
        data = read_bounded(self._root, name, STORE_MAX_FILE_BYTES, _CORRUPT)
        if sha256_bytes(data) != self._manifest.chunks[index]:
            raise StorageError(key=_CORRUPT, name=name)
        return data

    def _table(self, index: int) -> pa.Table:
        name = chunk_file_name(index)
        try:
            parquet = pq.ParquetFile(pa.BufferReader(self._verified(index)))
            if parquet.metadata.num_rows != 1:  # checked before anything is decoded
                raise StorageError(key=_CORRUPT, name=name)
            table = parquet.read()
        except (pa.ArrowException, OSError, ValueError):
            raise StorageError(key=_CORRUPT, name=name) from None
        if not self._matches_schema(table) or table.column(INDEX_COLUMN)[0].as_py() != index:
            raise StorageError(key=_CORRUPT, name=name)
        return table.replace_schema_metadata(None)

    def _matches_schema(self, table: pa.Table) -> bool:
        """Same columns and types, and written under this exact feature version."""
        expected = self._schema.arrow_schema()
        stored = (table.schema.metadata or {}).get(META_VERSION)
        same_columns = bool(table.schema.remove_metadata().equals(expected.remove_metadata()))
        return same_columns and stored == expected.metadata[META_VERSION]
