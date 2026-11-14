"""Speech, music and silence per chunk core (DECISIONS #63). Pure: the voice probabilities come from
the pipeline's detector (`media/vad.py`); this module only classifies windows and counts them.

Each whole 512-sample window (32 ms) gets one label, checked in this order:
  silence  RMS below SILENCE_DBFS
  speech   voice probability at or above SPEECH_PROB (Silero VAD)
  music    tonal: spectral flatness below MUSIC_FLATNESS (a steady tone is 0, white noise about 0.5)
  other    everything else (noise, effects, rumble)
A window counts for the chunk only when it lies inside the core (the overlap is context). The four
ratios are fractions of those windows and sum to 1; a core with no whole window gives all zeros.
"""

from collections.abc import Mapping
from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

from filmanalyser.core.chunk import Chunk
from filmanalyser.core.config import MUSIC_FLATNESS, SILENCE_DBFS, SPEECH_PROB, VOICE_WINDOW
from filmanalyser.core.errors import InputError

NAME = "speech_music"
VERSION = 3  # v3: 5.1 voice from the centre channel (#86); v2: tonal_ratio (#75)
FEATURES = ("silence_ratio", "speech_ratio", "tonal_ratio", "other_ratio")
SILENCE, SPEECH, MUSIC, OTHER = 0, 1, 2, 3
_LABEL_FEATURE = {SILENCE: "silence_ratio", SPEECH: "speech_ratio", MUSIC: "tonal_ratio"}
_TINY = 1e-12
_HANN = np.hanning(VOICE_WINDOW)


def _rms_dbfs(blocks: npt.NDArray[np.float64]) -> npt.NDArray[np.float64]:
    rms = np.sqrt(np.mean(blocks * blocks, axis=1))
    return 20 * np.log10(np.maximum(rms, _TINY))


def _flatness(blocks: npt.NDArray[np.float64]) -> npt.NDArray[np.float64]:
    """Spectral flatness: geometric over arithmetic mean of the power spectrum.

    0 is a pure tone and 1 is white noise."""
    power = np.abs(np.fft.rfft(blocks * _HANN, axis=1)) ** 2 + _TINY
    return np.exp(np.mean(np.log(power), axis=1)) / np.mean(power, axis=1)


def classify_windows(
    mono: npt.NDArray[np.float64], voice: npt.NDArray[np.float32], core_offset: int
) -> npt.NDArray[np.int64]:
    """One label per whole window of `mono` (the windows are those of `voice`, which covers the
    same signal). Windows that start before `core_offset` are labelled too; callers drop them."""
    count = min(len(voice), len(mono) // VOICE_WINDOW)
    blocks = mono[: count * VOICE_WINDOW].reshape(count, VOICE_WINDOW)
    silent = _rms_dbfs(blocks) < SILENCE_DBFS
    speech = np.asarray(voice[:count]) >= SPEECH_PROB
    tonal = _flatness(blocks) < MUSIC_FLATNESS
    labels = np.full(count, OTHER, dtype=np.int64)
    labels[tonal] = MUSIC
    labels[speech] = SPEECH
    labels[silent] = SILENCE
    return labels


def features_for(
    mono: npt.NDArray[np.float64], voice: npt.NDArray[np.float32], core_offset: int
) -> dict[str, float]:
    """The four ratios over the whole windows that lie inside the core."""
    labels = classify_windows(mono, voice, core_offset)
    starts = np.arange(len(labels)) * VOICE_WINDOW
    core = labels[starts >= core_offset]
    out = dict.fromkeys(FEATURES, 0.0)
    if core.size == 0:
        return out
    out["other_ratio"] = float(np.count_nonzero(core == OTHER)) / core.size
    for label, feature in _LABEL_FEATURE.items():
        out[feature] = float(np.count_nonzero(core == label)) / core.size
    return out


@dataclass(frozen=True)
class SpeechMusic:
    name: str = NAME
    version: int = VERSION
    features: tuple[str, ...] = FEATURES
    needs_audio: bool = True

    def extract(self, chunk: Chunk) -> Mapping[str, float]:
        audio = chunk.audio
        if audio is None or audio.voice is None:
            raise InputError(key="error.input.bad_setting", name="voice")
        mono = np.mean(audio.samples, axis=1, dtype=np.float64)
        return features_for(mono, audio.voice, chunk.audio_core_offset)


EXTRACTOR = SpeechMusic()
