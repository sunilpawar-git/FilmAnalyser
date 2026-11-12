"""One analysis run: decoder -> every registered extractor -> feature store, resuming at the store's
next chunk (DECISIONS #44, #45). This module is the only place the three pieces meet."""

import time
from collections.abc import Callable, Mapping
from pathlib import Path

from filmanalyser.core.chunk import Chunk
from filmanalyser.core.config import Config
from filmanalyser.core.errors import InputError
from filmanalyser.core.events import log_event
from filmanalyser.extractors.registry import ExtractorRegistry, discover
from filmanalyser.media.ffmpeg_stream import decode_chunks
from filmanalyser.media.paths import validate_input_path
from filmanalyser.storage.feature_store import FeatureStore
from filmanalyser.storage.files import sha256_file
from filmanalyser.storage.manifest import RunKey
from filmanalyser.storage.schema import ExtractorColumns, FeatureSchema

Observer = Callable[[int], None]


def schema_for(registry: ExtractorRegistry) -> FeatureSchema:
    """The feature schema, built from what each registered extractor declares (DECISIONS #49)."""
    return FeatureSchema(
        tuple(ExtractorColumns(e.name, e.version, tuple(e.features)) for e in registry)
    )


def validate_for_pipeline(config: Config) -> None:
    """Refuse a configuration the extractors cannot run under (DECISIONS #55)."""
    if config.overlap_frames < 1:
        raise InputError(key="error.input.bad_setting", name="overlap_seconds")


def extract_chunk(registry: ExtractorRegistry, chunk: Chunk) -> Mapping[str, Mapping[str, float]]:
    """Every extractor's features for one chunk, keyed by extractor name. Timed and logged."""
    began = time.perf_counter()
    outputs = {extractor.name: extractor.extract(chunk) for extractor in registry}
    log_event("chunk_extracted", index=chunk.index, extract_s=round(time.perf_counter() - began, 4))
    return outputs


def analyse(
    film: str | Path,
    out: str | Path,
    config: Config | None = None,
    *,
    on_decoded: Observer | None = None,
    on_stored: Observer | None = None,
) -> FeatureStore:
    """Analyse `film` into the store at `out`, resuming from whatever that store already holds.
    `on_decoded` and `on_stored` are observers (the kill-and-resume tests use them)."""
    settings = Config() if config is None else config
    validate_for_pipeline(settings)
    active = discover()
    path = validate_input_path(film)
    schema = schema_for(active)
    key = RunKey(sha256_file(path), schema.version, settings.geometry())
    store = FeatureStore.open(out, schema, key)
    log_event("run_start", film=path.name, next_chunk=store.next_chunk)
    if not store.complete:
        for chunk in decode_chunks(path, settings, start_chunk=store.next_chunk):
            if on_decoded is not None:
                on_decoded(chunk.index)
            outputs = extract_chunk(active, chunk)
            store.append(chunk.index, chunk.start_s, chunk.end_s, outputs)
            if on_stored is not None:
                on_stored(chunk.index)
        store.mark_complete()
    log_event("run_done", film=path.name, chunks=store.next_chunk)
    return store
