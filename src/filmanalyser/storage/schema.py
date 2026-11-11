"""The feature schema: the single source of truth for feature names, types and version.

A schema is the ordered list of extractors with their versions and the features each produces.
Its `version` is a hash of all of that plus the file layout, so any change (a bumped extractor, a
renamed or added feature) gives a different version and stored data is rejected, never mixed in
(DECISIONS #7, #19). Parquet types are fixed: `chunk_index` int32, everything else float64.
"""

import hashlib
import json
import math
import re
from collections.abc import Mapping
from dataclasses import dataclass

import pyarrow as pa

from filmanalyser.core.errors import StorageError

LAYOUT_VERSION = 1  # bump when the file layout itself changes (names, columns, metadata)
MANIFEST_NAME = "manifest.json"
INDEX_COLUMN, START_COLUMN, END_COLUMN = "chunk_index", "start_s", "end_s"
META_VERSION = b"filmanalyser.feature_version"
META_LAYOUT = b"filmanalyser.layout_version"
_NAME = re.compile(r"^[a-z][a-z0-9_]*$")


def _bad_schema(name: str) -> StorageError:
    return StorageError(key="error.storage.bad_schema", name=name)


def _bad_features(name: str) -> StorageError:
    return StorageError(key="error.storage.bad_features", name=name)


def chunk_file_name(index: int) -> str:
    """The one place a chunk file is named. Built from an integer only, never from user text."""
    if isinstance(index, bool) or not isinstance(index, int) or index < 0:
        raise _bad_features(INDEX_COLUMN)
    return f"chunk_{index:06d}.parquet"


@dataclass(frozen=True)
class ExtractorColumns:
    """One extractor's contribution: its name, version and the feature names it returns."""

    name: str
    version: int
    features: tuple[str, ...]


@dataclass(frozen=True)
class FeatureSchema:
    extractors: tuple[ExtractorColumns, ...]

    def __post_init__(self) -> None:
        if not self.extractors:
            raise _bad_schema("extractors")
        seen: set[str] = set()
        for ext in self.extractors:
            if not _NAME.match(ext.name) or ext.name in seen:
                raise _bad_schema(ext.name)
            seen.add(ext.name)
            if ext.version < 1 or not ext.features or len(set(ext.features)) != len(ext.features):
                raise _bad_schema(ext.name)
            for feature in ext.features:
                if not _NAME.match(feature):
                    raise _bad_schema(f"{ext.name}.{feature}")

    @property
    def columns(self) -> tuple[str, ...]:
        return tuple(f"{e.name}.{f}" for e in self.extractors for f in e.features)

    @property
    def version(self) -> str:
        """Hash of the layout and every extractor name, version and feature, in order."""
        plan = [[e.name, e.version, list(e.features)] for e in self.extractors]
        canonical = json.dumps([LAYOUT_VERSION, plan], separators=(",", ":")).encode()
        return hashlib.sha256(canonical).hexdigest()

    def arrow_schema(self) -> pa.Schema:
        fields = [pa.field(INDEX_COLUMN, pa.int32(), nullable=False)]
        fields += [pa.field(n, pa.float64(), nullable=False) for n in self.float_columns]
        meta = {META_VERSION: self.version.encode(), META_LAYOUT: str(LAYOUT_VERSION).encode()}
        return pa.schema(fields, metadata=meta)

    @property
    def float_columns(self) -> tuple[str, ...]:
        return (START_COLUMN, END_COLUMN, *self.columns)

    def row(self, outputs: Mapping[str, Mapping[str, float]]) -> dict[str, float]:
        """Flatten `{extractor: {feature: value}}` into column order, or raise if it does not
        match the schema exactly (no missing or extra extractors or features, finite numbers)."""
        declared = {e.name: e for e in self.extractors}
        if extra := next((n for n in outputs if n not in declared), None):
            raise _bad_features(extra)
        flat: dict[str, float] = {}
        for ext in self.extractors:
            given = outputs.get(ext.name)
            if given is None:
                raise _bad_features(ext.name)
            if extra := next((f for f in given if f not in ext.features), None):
                raise _bad_features(f"{ext.name}.{extra}")
            for feature in ext.features:
                flat[f"{ext.name}.{feature}"] = _number(given, feature, f"{ext.name}.{feature}")
        return flat


def _number(given: Mapping[str, float], feature: str, column: str) -> float:
    value = given.get(feature)
    if isinstance(value, bool) or not isinstance(value, int | float) or not math.isfinite(value):
        raise _bad_features(column)
    return float(value)
