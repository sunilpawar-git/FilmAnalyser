"""A miniature pipeline for the storage integration tests: real decoder, real store, one stand-in
extractor. (The production runner arrives in Phase 4; this wires the same three pieces.)

The extractor measures brightness and motion. Motion needs the frame *before* the first core
frame, so it only comes out right if the chunk's carried context is right: a resumed run that got
its overlap wrong would store different numbers."""

from collections.abc import Callable
from pathlib import Path

import numpy as np

from filmanalyser.core.chunk import Chunk
from filmanalyser.core.config import Config
from filmanalyser.media.ffmpeg_stream import decode_chunks
from filmanalyser.media.paths import validate_input_path
from filmanalyser.storage.feature_store import FeatureStore
from filmanalyser.storage.files import sha256_file
from filmanalyser.storage.manifest import RunKey
from filmanalyser.storage.schema import ExtractorColumns, FeatureSchema

CONFIG = Config(chunk_seconds=10.0, overlap_seconds=1.0, analysis_fps=10.0, frame_width=64)
SCHEMA = FeatureSchema((ExtractorColumns("luma", 1, ("mean", "motion")),))


def features(chunk: Chunk) -> dict[str, dict[str, float]]:
    luma = chunk.frames.mean(axis=(1, 2, 3))
    steps = np.abs(np.diff(luma[max(chunk.context_frames - 1, 0) :]))
    return {
        "luma": {"mean": float(luma[chunk.context_frames :].mean()), "motion": float(steps.mean())}
    }


def tree(directory: Path) -> dict[str, bytes]:
    """Every file of a store directory by name: what "byte-identical" is asserted over."""
    return {p.name: p.read_bytes() for p in sorted(directory.iterdir())}


def run_film(
    film: Path,
    directory: Path,
    on_decoded: Callable[[int], None] = lambda _index: None,
    on_stored: Callable[[int], None] = lambda _index: None,
) -> FeatureStore:
    """Analyse `film` into `directory`, resuming from whatever is already stored there."""
    path = validate_input_path(film)
    key = RunKey(sha256_file(path), SCHEMA.version, CONFIG.geometry())
    store = FeatureStore.open(directory, SCHEMA, key)
    if not store.complete:
        for chunk in decode_chunks(path, CONFIG, start_chunk=store.next_chunk):
            on_decoded(chunk.index)
            store.append(chunk.index, chunk.start_s, chunk.end_s, features(chunk))
            on_stored(chunk.index)
        store.mark_complete()
    return store
