"""The resume manifest: which chunks are finished, and for which film, features and settings.

Stored as canonical JSON (sorted keys, no timestamps, so equal runs give equal bytes). It is the
single truth about progress: a chunk file the manifest does not list is ignored and redone. A
manifest that cannot be parsed is a StorageError, never a crash and never a guess.
"""

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Self

from filmanalyser.core.config import STORE_MAX_FILE_BYTES
from filmanalyser.core.errors import StorageError
from filmanalyser.storage.files import read_bounded, write_atomic
from filmanalyser.storage.schema import LAYOUT_VERSION, MANIFEST_NAME

_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_KEYS = {"format", "input_hash", "feature_version", "geometry", "complete", "chunks"}
_CORRUPT = "error.storage.manifest_corrupt"


@dataclass(frozen=True)
class RunKey:
    """What a stored run is cached by (DECISIONS #19): the film, the features and the settings."""

    input_hash: str
    feature_version: str
    geometry: Mapping[str, float]


@dataclass(frozen=True)
class Manifest:
    key: RunKey
    chunks: tuple[str, ...] = ()  # sha256 of each finished chunk file, in chunk order
    complete: bool = False

    @property
    def finished(self) -> int:
        return len(self.chunks)

    def with_chunk(self, digest: str) -> Self:
        return replace(self, chunks=(*self.chunks, digest))

    def completed(self) -> Self:
        return replace(self, complete=True)

    def require(self, key: RunKey, name: str) -> None:
        """Reject a store that was made for a different film, feature version or settings."""
        if self.key.input_hash != key.input_hash:
            raise StorageError(key="error.storage.input_mismatch", name=name)
        if self.key.feature_version != key.feature_version:
            raise StorageError(key="error.storage.features_mismatch", name=name)
        if dict(self.key.geometry) != dict(key.geometry):
            raise StorageError(key="error.storage.settings_mismatch", name=name)

    def to_bytes(self) -> bytes:
        body = {
            "format": LAYOUT_VERSION,
            "input_hash": self.key.input_hash,
            "feature_version": self.key.feature_version,
            "geometry": dict(self.key.geometry),
            "complete": self.complete,
            "chunks": list(self.chunks),
        }
        return json.dumps(body, sort_keys=True, separators=(",", ":")).encode()


def _corrupt() -> StorageError:
    return StorageError(key=_CORRUPT, name=MANIFEST_NAME)


def _hex(value: Any) -> str:
    if not isinstance(value, str) or not _HEX64.match(value):
        raise _corrupt()
    return value


def _geometry(value: Any) -> dict[str, float]:
    if not isinstance(value, dict) or not value:
        raise _corrupt()
    for number in value.values():
        if isinstance(number, bool) or not isinstance(number, int | float):
            raise _corrupt()
    return dict(value)


def parse_manifest(data: bytes) -> Manifest:
    try:
        body = json.loads(data.decode("utf-8"))
    except ValueError:  # covers bad UTF-8 and bad JSON
        raise _corrupt() from None
    if not isinstance(body, dict) or set(body) != _KEYS or body["format"] != LAYOUT_VERSION:
        raise _corrupt()
    chunks, complete = body["chunks"], body["complete"]
    if not isinstance(chunks, list) or not isinstance(complete, bool):
        raise _corrupt()
    key = RunKey(
        _hex(body["input_hash"]), _hex(body["feature_version"]), _geometry(body["geometry"])
    )
    return Manifest(key, tuple(_hex(c) for c in chunks), complete)


def load_manifest(root: Path) -> Manifest | None:
    """The stored manifest, or None when the directory has none yet."""
    if not (root / MANIFEST_NAME).exists():
        return None
    return parse_manifest(read_bounded(root, MANIFEST_NAME, STORE_MAX_FILE_BYTES, _CORRUPT))


def save_manifest(root: Path, manifest: Manifest) -> None:
    write_atomic(root, MANIFEST_NAME, manifest.to_bytes())
