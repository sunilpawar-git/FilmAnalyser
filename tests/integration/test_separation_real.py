"""The real voice-separation model (DECISIONS #88). Run by `make separation-check` only: it needs
the `demucs` tool on PATH and the pinned model from `make separation-model` (84 MB, PyTorch), which
the project does not install and CI does not have. The stand-in test (test_separation_pipeline.py)
covers the same path in `make check`.

The case: a speech recording buried under a loud chord. The voice detector misses most of it on the
mix; on the separated voice it hears it again."""

from pathlib import Path

import numpy as np
import pytest

from filmanalyser.core.config import AUDIO_HIRES_RATE, AUDIO_RATE, SPEECH_PROB
from filmanalyser.media.audio import PcmFormat, decode_window
from filmanalyser.media.separation import default_model_dir, find_separator, separate_windows
from filmanalyser.media.vad import VoiceDetector

pytestmark = pytest.mark.separation

SPEECH = Path(__file__).resolve().parents[1] / "fixtures" / "speech_16k.wav"
DURATION_S = 5.9


def _chord(count: int, rate: int) -> np.ndarray:
    t = np.arange(count) / rate
    rng = np.random.default_rng(3)
    tones = sum(np.sin(2 * np.pi * f * t) for f in (220, 277, 330, 440, 554))
    return tones / 5 * (1 + 0.3 * np.sin(2 * np.pi * 3 * t)) + 0.05 * rng.standard_normal(count)


def test_speech_buried_under_music_is_heard_on_the_separated_voice(tmp_path: Path) -> None:
    detector = VoiceDetector.load()
    speech = decode_window(SPEECH, 0.0, DURATION_S, PcmFormat(2, AUDIO_HIRES_RATE))
    mix = (0.4 * speech + 0.5 * _chord(len(speech), AUDIO_HIRES_RATE)[:, None]).astype(np.float32)
    truth = detector.probabilities(decode_window(SPEECH, 0.0, DURATION_S, PcmFormat(1, AUDIO_RATE)))
    truth_mask = truth >= SPEECH_PROB
    mix_16k = mix[:: AUDIO_HIRES_RATE // AUDIO_RATE].mean(axis=1).astype(np.float32)
    on_mix = detector.probabilities(mix_16k)[: len(truth)] >= SPEECH_PROB

    separator = find_separator(default_model_dir())
    stems = separate_windows(separator, {0: (mix, AUDIO_HIRES_RATE)}, tmp_path)
    on_stem = detector.probabilities(stems[0])[: len(truth)] >= SPEECH_PROB

    mix_recall = float(np.mean(on_mix[truth_mask]))
    stem_recall = float(np.mean(on_stem[truth_mask]))
    assert mix_recall < 0.5  # the music hides the speech from the detector
    assert stem_recall > 0.8  # separation gives it back
    assert stem_recall > mix_recall + 0.3
