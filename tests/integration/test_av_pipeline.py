"""The combined video and audio pipeline on clips with known audio: the runner decodes audio per
chunk, runs the voice detector, and stores loudness and speech/music/silence beside the picture.

Ground truth: silence 0-2 s, a 0.5-amplitude 440 Hz tone 2-4 s, silence 4-6 s. With 2 s chunks the
cores are exactly those three spans, so each chunk has a known answer."""

from collections.abc import Callable
from pathlib import Path

import numpy as np
import pytest

from filmanalyser.core.config import LOUDNESS_ABS_GATE_LUFS, Config
from filmanalyser.extractors._kweighting import biquads
from filmanalyser.pipeline.runner import analyse
from filmanalyser.storage.feature_store import FeatureStore
from tests.fixtures.make_synthetic import make_av_clip, make_silent_clip
from tests.unit.test_loudness import _gain_db

TONE = "0.5*sin(2*PI*440*t)*between(t\\,2\\,4)"
CONFIG = Config(chunk_seconds=2.0, overlap_seconds=0.5, analysis_fps=12.0, frame_width=64)
# BS.1770 for this sine: K-weighting at 440 Hz (from the published 48 kHz coefficients) is not the
# 1 kHz value, so the reference is computed at the tone's own frequency.
K_440_DB = sum(_gain_db(stage, 440.0, 48000) for stage in biquads(48000))
TONE_LUFS = -0.691 + K_440_DB + 10 * np.log10(0.5**2 / 2)


def _run(film: Path, out: Path, **observers: Callable[[int], None]) -> dict[str, np.ndarray]:
    """Analyse `film` into `out` and return every stored column."""
    store: FeatureStore = analyse(film, out, CONFIG, **observers)
    return store.read_columns()


def test_each_chunk_reports_the_audio_it_contains(tmp_path: Path) -> None:
    film = make_av_clip(tmp_path / "av.mp4", 6.0, TONE)
    columns = _run(film, tmp_path / "store")
    assert len(columns["chunk_index"]) == 3
    lufs = columns["loudness.integrated_lufs"]
    assert lufs[0] == LOUDNESS_ABS_GATE_LUFS  # 0-2 s: silence
    assert lufs[1] == pytest.approx(TONE_LUFS, abs=0.2)  # 2-4 s: the tone
    # 4-6 s: silence, except the ring-out of the tone's abrupt stop at 4.0 s. The K-weighting filter
    # rings for about 50 ms after an abrupt stop (measured: rms 4e-2 at the stop, 2e-6 at 50 ms,
    # then float noise). BS.1770 counts that block as sound, so the core reads -46.7 LUFS, not the
    # floor. A real film's noise floor is far above it; the gate removes the true silence.
    assert LOUDNESS_ABS_GATE_LUFS < lufs[2] < -40.0
    assert columns["speech_music.silence_ratio"][0] == pytest.approx(1.0, abs=0.03)
    assert columns["speech_music.music_ratio"][1] == pytest.approx(1.0, abs=0.03)
    assert columns["speech_music.silence_ratio"][2] == pytest.approx(1.0, abs=0.05)


def test_video_features_are_stored_alongside_the_audio_ones(tmp_path: Path) -> None:
    film = make_av_clip(tmp_path / "av.mp4", 6.0, TONE)
    names = set(_run(film, tmp_path / "store"))
    assert {"shot_cuts.cuts", "color.brightness", "loudness.peak_dbfs"} <= names
    assert {"speech_music.speech_ratio", "speech_music.other_ratio"} <= names


def test_a_film_without_audio_is_analysed_without_the_audio_extractors(tmp_path: Path) -> None:
    film = make_silent_clip(tmp_path / "silent.mp4", 4.0)
    columns = _run(film, tmp_path / "store")
    assert "shot_cuts.cuts" in columns
    assert not any(name.startswith(("loudness.", "speech_music.")) for name in columns)


def test_the_audio_run_is_byte_identical_when_repeated(tmp_path: Path) -> None:
    film = make_av_clip(tmp_path / "av.mp4", 6.0, TONE)
    _run(film, tmp_path / "first")
    _run(film, tmp_path / "second")
    first = {p.name: p.read_bytes() for p in sorted((tmp_path / "first").iterdir())}
    second = {p.name: p.read_bytes() for p in sorted((tmp_path / "second").iterdir())}
    assert first == second


def test_resuming_after_a_kill_equals_an_uninterrupted_run(tmp_path: Path) -> None:
    film = make_av_clip(tmp_path / "av.mp4", 6.0, TONE)
    reference = _run(film, tmp_path / "reference")

    def interrupt(index: int) -> None:
        if index == 1:
            raise KeyboardInterrupt  # stands in for a kill after chunk 1 is stored

    with pytest.raises(KeyboardInterrupt):
        _run(film, tmp_path / "resumed", on_stored=interrupt)
    got = _run(film, tmp_path / "resumed")
    expected = reference
    assert set(got) == set(expected)
    for name in expected:
        assert np.array_equal(got[name], expected[name]), name
