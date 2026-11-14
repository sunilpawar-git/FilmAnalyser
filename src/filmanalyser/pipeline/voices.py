"""Opt-in voice separation in the pipeline (DECISIONS #88): where the background is loud, the voice
detector also hears the voice stem that Demucs separates from the mix, and a window is speech when
either the mix or the stem says so.

Chunks are separated ahead of the pipeline, a batch at a time. Each upcoming window is decoded on
its own (cheap, and aligned like the pipeline's own audio); its background level decides whether it
is separated (SEPARATION_BED_DBFS); the chosen windows go to one Demucs run. A resumed run starts
the batches at its first chunk, so stems never depend on chunks that were not decoded.
"""

import dataclasses
import tempfile
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import numpy as np
import numpy.typing as npt

from filmanalyser.core.chunk import Chunk, Samples, expected_chunks, span_for
from filmanalyser.core.config import (
    AUDIO_HIRES_RATE,
    AUDIO_RATE,
    SEPARATION_BATCH,
    SEPARATION_BED_DBFS,
    Config,
)
from filmanalyser.core.events import log_event
from filmanalyser.media.audio import AudioStream, PcmFormat, audio_window
from filmanalyser.media.separation import Separator, background_dbfs, separate_windows
from filmanalyser.media.vad import VoiceDetector, dialogue_signal


@dataclass(frozen=True)
class FilmAudio:
    """Where a film's audio is and how it sits on the container clock."""

    path: Path
    picture_start_s: float
    stream: AudioStream
    duration_s: float


class Stems(Protocol):
    """Anything that gives a chunk's voice stem, or None for a chunk that is not separated."""

    def stem_for(self, index: int) -> npt.NDArray[np.float32] | None: ...


class StemSource:
    """Voice stems for chunks, separated one batch ahead of the pipeline."""

    def __init__(
        self, film: FilmAudio, config: Config, separator: Separator, detector: VoiceDetector
    ) -> None:
        self._film, self._config = film, config
        self._separator, self._detector = separator, detector
        frames = round(film.duration_s * config.analysis_fps)
        self._count = expected_chunks(frames, config.frames_per_chunk)
        self._visited: set[int] = set()
        self._stems: dict[int, npt.NDArray[np.float32]] = {}

    def stem_for(self, index: int) -> npt.NDArray[np.float32] | None:
        """The voice stem of chunk `index`, or None when its background is too quiet to need one."""
        if index not in self._visited:
            self._fill(index)
        return self._stems.pop(index, None)

    def _window(self, index: int, rate: int) -> Samples:
        config = self._config
        span = span_for(index, config.frames_per_chunk, config.overlap_frames)
        start = span.context_start / config.analysis_fps  # as the chunk's own audio (media/audio)
        end = span.core_end / config.analysis_fps
        film = self._film
        pcm = PcmFormat(film.stream.channels, rate)
        return audio_window(
            film.path, film.picture_start_s + start, film.stream.start_s, end - start, pcm
        )

    def _needs_separation(self, index: int) -> bool:
        mono = dialogue_signal(self._window(index, AUDIO_RATE))
        return background_dbfs(mono, self._detector.probabilities(mono)) >= SEPARATION_BED_DBFS

    def _fill(self, first: int) -> None:
        batch = range(first, max(first + 1, min(first + SEPARATION_BATCH, self._count)))
        self._visited.update(batch)
        chosen = [index for index in batch if self._needs_separation(index)]
        log_event("separation_batch", first=first, chunks=len(batch), separated=len(chosen))
        if not chosen:
            return
        windows = {
            index: (self._window(index, AUDIO_HIRES_RATE), AUDIO_HIRES_RATE) for index in chosen
        }
        with tempfile.TemporaryDirectory(prefix="filmanalyser-separation-") as work:
            self._stems.update(separate_windows(self._separator, windows, Path(work)))


def _fit(stem: npt.NDArray[np.float32], count: int) -> npt.NDArray[np.float32]:
    """The stem at exactly `count` samples (the chunk's own audio length): padded or cut."""
    out = np.zeros(count, dtype=np.float32)
    out[: min(count, len(stem))] = stem[:count]
    return out


def attach_separated_voice(
    chunks: Iterable[Chunk], stems: Stems, detector: VoiceDetector
) -> Iterator[Chunk]:
    """Each chunk whose voice probability is the larger of the mix's and its voice stem's."""
    for chunk in chunks:
        audio = chunk.audio
        stem = None if audio is None or audio.voice is None else stems.stem_for(chunk.index)
        if audio is None or audio.voice is None or stem is None:
            yield chunk
            continue
        separated = detector.probabilities(_fit(stem, len(audio.samples)))
        voice = np.maximum(audio.voice, separated[: len(audio.voice)])
        yield dataclasses.replace(chunk, audio=dataclasses.replace(audio, voice=voice))
