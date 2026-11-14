"""One analysis run: decoder -> every registered extractor -> feature store, resuming at the store's
next chunk (DECISIONS #44, #45). This module is the only place the three pieces meet."""

import time
from collections.abc import Callable, Iterator, Mapping
from pathlib import Path

from filmanalyser.core.chunk import Chunk
from filmanalyser.core.config import FIVE_ONE_CHANNELS, Config
from filmanalyser.core.errors import InputError
from filmanalyser.core.events import log_event
from filmanalyser.extractors.registry import ExtractorRegistry, discover
from filmanalyser.media.audio import AudioStream, audio_stream
from filmanalyser.media.ffmpeg_stream import decode_chunks
from filmanalyser.media.paths import validate_input_path
from filmanalyser.media.probe import probe_video
from filmanalyser.media.separation import Separator, default_model_dir, find_separator
from filmanalyser.media.vad import VoiceDetector, attach_voice
from filmanalyser.pipeline.voices import FilmAudio, StemSource, attach_separated_voice
from filmanalyser.storage.feature_store import FeatureStore
from filmanalyser.storage.files import sha256_file
from filmanalyser.storage.manifest import RunKey
from filmanalyser.storage.schema import ExtractorColumns, FeatureSchema

Observer = Callable[[int], None]
__all__ = [
    "analyse",
    "chunk_stream",
    "default_model_dir",
    "extract_chunk",
    "schema_for",
    "select_extractors",
]


def schema_for(registry: ExtractorRegistry) -> FeatureSchema:
    """The feature schema, built from what each registered extractor declares (DECISIONS #49)."""
    return FeatureSchema(
        tuple(ExtractorColumns(e.name, e.version, tuple(e.features)) for e in registry)
    )


def select_extractors(registry: ExtractorRegistry, has_audio: bool) -> ExtractorRegistry:
    """The extractors this run can use: audio extractors are dropped for a film without audio, and
    the run then stores video features only (DECISIONS #64)."""
    chosen = ExtractorRegistry()
    for extractor in registry:
        if extractor.needs_audio and not has_audio:
            log_event("audio_extractor_skipped", name=extractor.name)
            continue
        chosen.register(extractor)
    return chosen


def chunk_stream(
    path: Path,
    config: Config,
    start: int,
    audio: AudioStream | None,
    separator: Separator | None = None,
) -> Iterator[Chunk]:
    """The decoded chunks of a run. With audio, each chunk also carries its audio and speech
    probabilities (the voice model is loaded once for the run and verified before use). With a
    separator, chunks with a loud background also hear their separated voice (DECISIONS #88); a 5.1
    track is not separated, because its centre channel already carries the dialogue (#86)."""
    if audio is None:
        return decode_chunks(path, config, start_chunk=start)
    chunks = decode_chunks(
        path, config, start_chunk=start, channels=audio.channels, audio_start_s=audio.start_s
    )
    detector = VoiceDetector.load()
    voiced = attach_voice(chunks, detector)
    if separator is None or audio.channels == FIVE_ONE_CHANNELS:
        if separator is not None:
            log_event("separation_skipped", reason="five_one_centre")
        return voiced
    info = probe_video(path)
    film = FilmAudio(path, info.start_s, audio, info.duration_s)
    return attach_separated_voice(voiced, StemSource(film, config, separator, detector), detector)


def separator_for(config: Config) -> Separator | None:
    """The verified separator when the run asks for one (found before any decoding starts)."""
    if not config.separate_voices:
        return None
    return find_separator(Path(config.separation_model))


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
    path = validate_input_path(film)
    registry = discover()
    audio = audio_stream(path) if any(e.needs_audio for e in registry) else None
    active = select_extractors(registry, has_audio=audio is not None)
    schema = schema_for(active)
    key = RunKey(sha256_file(path), schema.version, settings.geometry())
    store = FeatureStore.open(out, schema, key)
    separator = separator_for(settings)
    log_event("run_start", film=path.name, next_chunk=store.next_chunk)
    if not store.complete:
        for chunk in chunk_stream(path, settings, store.next_chunk, audio, separator):
            if on_decoded is not None:
                on_decoded(chunk.index)
            outputs = extract_chunk(active, chunk)
            store.append(chunk.index, chunk.start_s, chunk.end_s, outputs)
            if on_stored is not None:
                on_stored(chunk.index)
        store.mark_complete()
    log_event("run_done", film=path.name, chunks=store.next_chunk)
    return store
