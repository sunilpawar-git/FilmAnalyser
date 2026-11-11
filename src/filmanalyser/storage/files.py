"""The only module in storage/ that touches the file system (a guard enforces that).

Safety rules, all here so they exist once:
- the output directory is resolved once; every file lives directly inside it and is named by a
  plain name (no separators, no `..`); a symlink standing in for a file is refused;
- writes are atomic: a private temp file in the same directory, fsync, then `os.replace`, so a
  reader (or a crash) sees the old file or the complete new one, never half of it;
- reads are bounded by size; errors carry basenames only (never full paths).
"""

import contextlib
import hashlib
import os
import tempfile
from pathlib import Path

from filmanalyser.core.config import HASH_BLOCK_BYTES
from filmanalyser.core.errors import InputError, StorageError

TEMP_PREFIX = ".tmp-"
TEMP_SUFFIX = ".part"


def _base(text: str) -> str:
    return os.path.basename(text).replace("\x00", "?")


def _bad_directory(text: str) -> StorageError:
    return StorageError(key="error.storage.bad_directory", name=_base(text))


def open_directory(raw: str | os.PathLike[str]) -> Path:
    """The chosen output directory: created if absent, resolved to its real path."""
    text = os.fspath(raw)
    if not text.strip() or "\x00" in text:
        raise _bad_directory(text)
    try:
        path = Path(text).resolve()
        path.mkdir(parents=True, exist_ok=True)
    except (OSError, RuntimeError):
        raise _bad_directory(text) from None
    return path  # mkdir(exist_ok) already refused an existing file, so this is a directory


def confined_file(root: Path, name: str) -> Path:
    """`root/name`, where `name` must be a plain file name and not a symlink."""
    if not name or name in {".", ".."} or name != _base(name) or "\\" in name or "\x00" in name:
        raise _bad_directory(name)
    path = root / name
    if path.is_symlink():
        raise _bad_directory(name)
    return path


def write_atomic(root: Path, name: str, data: bytes) -> None:
    """Write `data` to `root/name` so that it appears whole or not at all."""
    target = confined_file(root, name)
    tmp_name = ""
    try:
        fd, tmp_name = tempfile.mkstemp(dir=root, prefix=TEMP_PREFIX, suffix=TEMP_SUFFIX)
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, target)
        _sync_directory(root)
    except OSError:
        if tmp_name:
            with contextlib.suppress(OSError):
                os.unlink(tmp_name)
        raise StorageError(key="error.storage.write_failed", name=_base(name)) from None


def _sync_directory(root: Path) -> None:
    """Make the rename itself durable (best effort: not every file system allows it)."""
    with contextlib.suppress(OSError):
        fd = os.open(root, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)


def read_bounded(root: Path, name: str, limit: int, error_key: str) -> bytes:
    """The whole file, or StorageError(`error_key`) if it is missing, unreadable or over `limit`."""
    path = confined_file(root, name)
    try:
        with path.open("rb") as handle:
            data = handle.read(limit + 1)
    except OSError:
        raise StorageError(key=error_key, name=_base(name)) from None
    if len(data) > limit:
        raise StorageError(key=error_key, name=_base(name))
    return data


def remove_stale_temp(root: Path) -> int:
    """Delete temp files a killed run left behind; returns how many."""
    stale = [
        p for p in root.glob(f"{TEMP_PREFIX}*{TEMP_SUFFIX}") if p.is_file() and not p.is_symlink()
    ]
    for path in stale:
        path.unlink(missing_ok=True)
    return len(stale)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    """Digest of a (large) input film, read in fixed-size blocks so memory stays flat."""
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            while block := handle.read(HASH_BLOCK_BYTES):
                digest.update(block)
    except OSError:
        raise InputError(key="error.input.unreadable", name=_base(str(path))) from None
    return digest.hexdigest()
