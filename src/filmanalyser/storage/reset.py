"""Clear a store so a run starts from the first chunk (`--fresh`). Only the store's own files go:
the manifest, the chunk files and stale temp files. Anything else in the folder stays."""

from pathlib import Path

from filmanalyser.core.events import log_event
from filmanalyser.storage.files import TEMP_PREFIX, TEMP_SUFFIX, open_directory, remove_matching
from filmanalyser.storage.schema import CHUNK_GLOB, MANIFEST_NAME


def clear_store(directory: str | Path) -> int:
    """Remove the store's files from `directory` (created if absent); returns how many. The
    manifest goes first: a store without one is empty, so a crash part-way leaves no half store."""
    root = open_directory(directory)
    removed = remove_matching(root, (MANIFEST_NAME,))
    removed += remove_matching(root, (CHUNK_GLOB, f"{TEMP_PREFIX}*{TEMP_SUFFIX}"))
    log_event("store_cleared", files=removed)
    return removed
