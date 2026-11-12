"""Speech / music / silence per chunk core (pure: the voice probabilities are given, not computed).

Labels per 512-sample window (32 ms): silence (RMS below SILENCE_DBFS), speech (voice probability at
or above SPEECH_PROB), music (non-speech, non-silent, and tonal: spectral flatness below
MUSIC_FLATNESS), other (non-speech, non-silent, noisy). The four ratios sum to 1 over the core.
Ground truth on synthetic signals: a steady tone is tonal, white noise is not, silence is silence.
"""

import numpy as np
import pytest

from filmanalyser.core.chunk import Audio, Chunk
from filmanalyser.core.config import AUDIO_RATE, SPEECH_PROB, VOICE_WINDOW
from filmanalyser.core.errors import InputError
from filmanalyser.core.extractor import Extractor
from filmanalyser.extractors.speech_music import (
    EXTRACTOR,
    FEATURES,
    classify_windows,
    features_for,
)

RATE = AUDIO_RATE
WINDOW_S = VOICE_WINDOW / RATE
TOLERANCE = 0.03  # one window in a second is about 0.03 of the ratio


def _tone(seconds: float, amplitude: float = 0.5) -> np.ndarray:
    t = np.arange(round(seconds * RATE)) / RATE
    return (amplitude * np.sin(2 * np.pi * 440.0 * t)).astype(np.float32)


def _noise(seconds: float, amplitude: float = 0.3, seed: int = 1) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return (amplitude * rng.standard_normal(round(seconds * RATE))).astype(np.float32)


def _silence(seconds: float) -> np.ndarray:
    return np.zeros(round(seconds * RATE), dtype=np.float32)


def _voice(samples: np.ndarray, value: float) -> np.ndarray:
    return np.full(len(samples) // VOICE_WINDOW, value, dtype=np.float32)


def _features(mono: np.ndarray, voice: np.ndarray, core_offset: int = 0) -> dict[str, float]:
    return features_for(mono.astype(np.float64), voice, core_offset)


def test_the_extractor_is_registered_as_needing_audio() -> None:
    assert isinstance(EXTRACTOR, Extractor)
    assert EXTRACTOR.name == "speech_music"
    assert EXTRACTOR.features == ("silence_ratio", "speech_ratio", "music_ratio", "other_ratio")
    assert EXTRACTOR.features == FEATURES
    assert EXTRACTOR.needs_audio is True


def test_silence_is_silence() -> None:
    out = _features(_silence(2.0), _voice(_silence(2.0), 0.0))
    assert out["silence_ratio"] == pytest.approx(1.0)
    assert sum(out.values()) == pytest.approx(1.0)


def test_a_steady_tone_is_music() -> None:
    tone = _tone(2.0)
    out = _features(tone, _voice(tone, 0.0))
    assert out["music_ratio"] == pytest.approx(1.0, abs=TOLERANCE)


def test_white_noise_is_other_not_music() -> None:
    noise = _noise(2.0)
    out = _features(noise, _voice(noise, 0.0))
    assert out["other_ratio"] == pytest.approx(1.0, abs=TOLERANCE)
    assert out["music_ratio"] == pytest.approx(0.0, abs=TOLERANCE)


def test_a_voiced_window_is_speech_whatever_it_sounds_like() -> None:
    tone = _tone(2.0)
    out = _features(tone, _voice(tone, 0.9))
    assert out["speech_ratio"] == pytest.approx(1.0, abs=TOLERANCE)
    assert out["music_ratio"] == pytest.approx(0.0, abs=TOLERANCE)


def test_the_speech_threshold_is_inclusive_at_its_value() -> None:
    tone = _tone(1.0)
    just_below = _features(tone, _voice(tone, SPEECH_PROB - 0.01))
    at = _features(tone, _voice(tone, SPEECH_PROB))
    assert just_below["speech_ratio"] == pytest.approx(0.0)
    assert at["speech_ratio"] == pytest.approx(1.0, abs=TOLERANCE)


def test_quiet_audio_is_silence_even_when_the_model_says_speech() -> None:
    quiet = _tone(1.0, amplitude=0.0001)  # about -80 dBFS: below the silence line
    out = _features(quiet, _voice(quiet, 0.99))
    assert out["silence_ratio"] == pytest.approx(1.0)


def test_half_silence_then_tone_splits_the_ratios() -> None:
    mono = np.concatenate([_silence(1.0), _tone(1.0)])
    out = _features(mono, _voice(mono, 0.0))
    assert out["silence_ratio"] == pytest.approx(0.5, abs=TOLERANCE)
    assert out["music_ratio"] == pytest.approx(0.5, abs=TOLERANCE)


def test_the_context_before_the_core_is_not_counted() -> None:
    context = _noise(1.0)
    core = _silence(1.0)
    mono = np.concatenate([context, core])
    offset = len(context)
    out = _features(mono, _voice(mono, 0.0), core_offset=offset)
    assert out["silence_ratio"] == pytest.approx(1.0, abs=TOLERANCE)
    assert out["other_ratio"] == pytest.approx(0.0, abs=TOLERANCE)


def test_a_core_shorter_than_one_window_gives_zeros() -> None:
    mono = _tone(0.01)  # 160 samples: less than one 512-sample window
    out = _features(mono, _voice(mono, 0.0))
    assert set(out.values()) == {0.0}


def test_classify_windows_labels_each_whole_window() -> None:
    mono = np.concatenate([_silence(WINDOW_S * 4), _tone(WINDOW_S * 4)]).astype(np.float64)
    labels = classify_windows(mono, _voice(mono, 0.0), core_offset=0)
    assert labels.shape == (len(mono) // VOICE_WINDOW,)
    assert set(labels[:4]) == {0}  # silence
    assert set(labels[4:8]) == {2}  # music


def test_extract_reads_the_chunk_audio_and_its_voice() -> None:
    tone = _tone(2.0)
    frames = np.zeros((2, 2, 2, 3), dtype=np.uint8)
    chunk = Chunk(
        index=0, start_s=0.0, end_s=2.0, fps=1.0, frames=frames, context_frames=0,
        audio=Audio(rate=RATE, start_s=0.0, samples=tone.reshape(-1, 1), voice=_voice(tone, 0.0)),
    )  # fmt: skip
    out = EXTRACTOR.extract(chunk)
    assert out["music_ratio"] == pytest.approx(1.0, abs=TOLERANCE)


def test_extract_refuses_a_chunk_without_voice_probabilities() -> None:
    tone = _tone(1.0)
    frames = np.zeros((1, 2, 2, 3), dtype=np.uint8)
    chunk = Chunk(
        index=0, start_s=0.0, end_s=1.0, fps=1.0, frames=frames, context_frames=0,
        audio=Audio(rate=RATE, start_s=0.0, samples=tone.reshape(-1, 1)),
    )  # fmt: skip
    with pytest.raises(InputError, match="voice"):
        EXTRACTOR.extract(chunk)
