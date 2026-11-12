"""The Silero detector on real inference: shape, determinism, and what it says about non-speech.

Limitation, recorded in EXECUTION_PLAN (pending item P5-2): no speech recording is kept in the repo,
so speech *accuracy* is not measured here. These tests check that silence and tones are not read as
speech, and that the output is well-formed and deterministic. Speech is checked on real footage."""

import wave
from pathlib import Path

import numpy as np
import pytest

from filmanalyser.core.chunk import Audio, Chunk
from filmanalyser.core.config import AUDIO_RATE, SPEECH_PROB, VOICE_WINDOW
from filmanalyser.extractors.speech_music import features_for
from filmanalyser.media.vad import VoiceDetector, attach_voice


@pytest.fixture(scope="module")
def detector() -> VoiceDetector:
    return VoiceDetector.load()


def _tone(seconds: float, freq: float = 440.0, amplitude: float = 0.5) -> np.ndarray:
    t = np.arange(round(seconds * AUDIO_RATE)) / AUDIO_RATE
    return (amplitude * np.sin(2 * np.pi * freq * t)).astype(np.float32)


def test_one_probability_per_whole_window(detector: VoiceDetector) -> None:
    signal = np.zeros(10 * VOICE_WINDOW + 100, dtype=np.float32)
    probs = detector.probabilities(signal)
    assert probs.shape == (10,)  # the 100-sample tail has no window
    assert probs.dtype == np.float32


def test_silence_is_not_speech(detector: VoiceDetector) -> None:
    probs = detector.probabilities(np.zeros(2 * AUDIO_RATE, dtype=np.float32))
    assert float(np.max(probs)) < 0.05


def test_a_steady_tone_is_not_speech(detector: VoiceDetector) -> None:
    probs = detector.probabilities(_tone(2.0))
    assert float(np.max(probs)) < 0.5


def test_probabilities_are_within_zero_and_one(detector: VoiceDetector) -> None:
    rng = np.random.default_rng(7)
    noise = (0.3 * rng.standard_normal(AUDIO_RATE)).astype(np.float32)
    probs = detector.probabilities(np.concatenate([noise, _tone(1.0)]))
    assert np.all(probs >= 0.0) and np.all(probs <= 1.0)
    assert np.isfinite(probs).all()


def test_the_same_input_gives_the_same_output(detector: VoiceDetector) -> None:
    signal = _tone(1.5)
    first = detector.probabilities(signal)
    second = detector.probabilities(signal)
    assert np.array_equal(first, second)


def test_attach_voice_adds_one_probability_per_window(detector: VoiceDetector) -> None:
    samples = _tone(1.0).reshape(-1, 1)
    frames = np.zeros((2, 2, 2, 3), dtype=np.uint8)
    chunk = Chunk(
        index=0, start_s=0.0, end_s=1.0, fps=2.0, frames=frames, context_frames=0,
        audio=Audio(rate=AUDIO_RATE, start_s=0.0, samples=samples),
    )  # fmt: skip
    (out,) = attach_voice([chunk], detector)
    assert out.audio is not None and out.audio.voice is not None
    assert out.audio.voice.shape == (AUDIO_RATE // VOICE_WINDOW,)


def test_attach_voice_leaves_a_chunk_without_audio_alone(detector: VoiceDetector) -> None:
    frames = np.zeros((2, 2, 2, 3), dtype=np.uint8)
    chunk = Chunk(index=0, start_s=0.0, end_s=1.0, fps=2.0, frames=frames, context_frames=0)
    (out,) = attach_voice([chunk], detector)
    assert out is chunk


SPEECH = Path(__file__).resolve().parents[1] / "fixtures" / "speech_16k.wav"
# Generated once with macOS text-to-speech (`say -v Samantha`, then 16 kHz mono PCM). Synthetic
# speech, not a recording of a person, so it shows the detector responds to speech; it does not
# measure accuracy on real dialogue (EXECUTION_PLAN pending item P5-1).


def _read_mono_16k(path: Path) -> np.ndarray:
    with wave.open(str(path)) as wav:
        assert wav.getframerate() == AUDIO_RATE and wav.getnchannels() == 1
        raw = wav.readframes(wav.getnframes())
    return np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0


def test_synthetic_speech_is_detected_as_speech(detector: VoiceDetector) -> None:
    probs = detector.probabilities(_read_mono_16k(SPEECH))
    assert float(np.mean(probs >= SPEECH_PROB)) > 0.85  # measured 0.95 when the fixture was made
    assert float(np.max(probs)) > 0.9


def test_speech_is_labelled_speech_by_the_classifier(detector: VoiceDetector) -> None:
    mono = _read_mono_16k(SPEECH).astype(np.float64)
    out = features_for(mono, detector.probabilities(mono.astype(np.float32)), core_offset=0)
    assert out["speech_ratio"] > 0.85
    assert out["silence_ratio"] < 0.15  # the pauses between sentences are silence (measured 0.09)
