"""The opt-in voice separation path end to end (DECISIONS #88), with a stand-in `demucs` on PATH
(tests/fixtures/fake_demucs.py) so it runs without PyTorch. The stand-in returns a known speech
recording as the voice stem; the real model is checked by `make separation-check`.

What is checked: chunks with a loud background are separated in one batch, quiet ones and 5.1
films are not, the stem's speech reaches the stored speech ratio, and a failing or hanging tool
stops the run with its own message."""

import hashlib
import json
import logging
import os
import stat
import subprocess
import sys
import wave
from pathlib import Path

import numpy as np
import pytest

from filmanalyser.core.chunk import Audio, Chunk
from filmanalyser.core.config import AUDIO_HIRES_RATE, AUDIO_RATE, SPEECH_PROB, Config
from filmanalyser.core.errors import DecodeError
from filmanalyser.media import separation
from filmanalyser.media.separation import separate_windows
from filmanalyser.media.vad import VoiceDetector
from filmanalyser.pipeline.runner import analyse
from filmanalyser.pipeline.voices import attach_separated_voice
from tests.fixtures.make_synthetic import av_clip_argv

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
SPEECH = FIXTURES / "speech_16k.wav"
# A loud chord with a swell: music, not speech, at about -12 dBFS (above SEPARATION_BED_DBFS)
LOUD = "0.25*(sin(2*PI*220*t)+sin(2*PI*277*t)+sin(2*PI*330*t))*(1+0.3*sin(2*PI*2*t))"
QUIET = "0.002*sin(2*PI*220*t)"  # about -57 dBFS: below the silence floor, no background
BASE = {"chunk_seconds": 2.0, "overlap_seconds": 0.5, "analysis_fps": 12.0, "frame_width": 64}


@pytest.fixture(scope="module")
def detector() -> VoiceDetector:
    return VoiceDetector.load()


@pytest.fixture
def fake_demucs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A `demucs` on PATH that returns SPEECH as the voice stem, and a model folder it accepts."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    tool = bin_dir / "demucs"
    body = (FIXTURES / "fake_demucs.py").read_text(encoding="utf-8")
    tool.write_text(f"#!{sys.executable} -I\n{body}", encoding="utf-8")
    tool.chmod(tool.stat().st_mode | stat.S_IXUSR)
    monkeypatch.setenv("PATH", str(bin_dir) + os.pathsep + os.environ["PATH"])
    monkeypatch.setenv("FAKE_STEM", str(SPEECH))
    monkeypatch.setenv("FAKE_LOG", str(tmp_path / "runs.log"))
    model = tmp_path / "model"
    model.mkdir()
    (model / "w.th").write_bytes(b"weights")
    pins = {"w.th": hashlib.sha256(b"weights").hexdigest()}
    monkeypatch.setattr(separation, "separation_pins", lambda: pins)
    return model


def _clip(tmp_path: Path, expr: str, layout: str = "stereo") -> Path:
    out = tmp_path / f"{layout}.mp4"
    channels = {"stereo": 2, "5.1": 6}[layout]
    subprocess.run(av_clip_argv(out, 6.0, "|".join([expr] * channels), layout=layout), check=True)
    return out


def _runs(tmp_path: Path) -> list[str]:
    log = tmp_path / "runs.log"
    return log.read_text(encoding="utf-8").splitlines() if log.exists() else []


def _speech(film: Path, out: Path, model: Path | None) -> np.ndarray:
    on = {"separate_voices": True, "separation_model": str(model)} if model else {}
    store = analyse(film, out, Config(**BASE, **on))  # type: ignore[arg-type]
    return store.read_columns()["speech_music.speech_ratio"]


# ---- the run -------------------------------------------------------------------------------------


def test_a_batch_of_windows_is_separated_in_one_run(fake_demucs: Path, tmp_path: Path) -> None:
    separator = separation.find_separator(fake_demucs)
    window = np.zeros((AUDIO_HIRES_RATE * 3, 2), dtype=np.float32)
    stems = separate_windows(
        separator, {4: (window, AUDIO_HIRES_RATE), 5: (window, AUDIO_HIRES_RATE)}, tmp_path
    )
    assert set(stems) == {4, 5}
    assert all(len(stem) == 3 * AUDIO_RATE for stem in stems.values())  # mono at AUDIO_RATE
    assert _runs(tmp_path) == ["chunk_000004.wav chunk_000005.wav"]


def test_a_failing_tool_stops_with_its_message(
    fake_demucs: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FAKE_FAIL", "1")
    window = np.zeros((AUDIO_HIRES_RATE, 2), dtype=np.float32)
    with pytest.raises(DecodeError) as caught:
        separate_windows(separation.find_separator(fake_demucs), {0: (window, 48000)}, tmp_path)
    assert caught.value.key == "error.decode.separation_failed"
    assert caught.value.fields["code"] == 3
    assert "fake demucs failed" in str(caught.value)


def test_a_hanging_tool_is_stopped(
    fake_demucs: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FAKE_SLEEP", "5")
    monkeypatch.setattr(separation, "SEPARATION_TIMEOUT_S", 0.5)
    window = np.zeros((AUDIO_HIRES_RATE, 2), dtype=np.float32)
    with pytest.raises(DecodeError) as caught:
        separate_windows(separation.find_separator(fake_demucs), {0: (window, 48000)}, tmp_path)
    assert caught.value.fields["code"] == -1


# ---- the merge -----------------------------------------------------------------------------------


class _Stems:
    def __init__(self, stem: np.ndarray | None) -> None:
        self.stem = stem

    def stem_for(self, index: int) -> np.ndarray | None:
        return self.stem


def _speech_signal() -> np.ndarray:
    with wave.open(str(SPEECH)) as wav:
        raw = wav.readframes(wav.getnframes())
    return np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0


def _chunk(samples: np.ndarray | None, voice: np.ndarray | None) -> Chunk:
    audio = None
    if samples is not None:
        audio = Audio(rate=AUDIO_RATE, start_s=0.0, samples=samples[:, None], voice=voice)
    frames = np.zeros((2, 2, 2, 3), dtype=np.uint8)
    return Chunk(
        index=0, start_s=0.0, end_s=1.0, fps=2.0, frames=frames, context_frames=0, audio=audio
    )


def test_a_window_is_speech_when_the_mix_or_the_stem_says_so(detector: VoiceDetector) -> None:
    speech = _speech_signal()
    silent_mix = np.zeros_like(speech)
    mix_voice = detector.probabilities(silent_mix)
    (out,) = attach_separated_voice([_chunk(silent_mix, mix_voice)], _Stems(speech), detector)
    assert out.audio is not None and out.audio.voice is not None
    assert float(np.mean(out.audio.voice >= SPEECH_PROB)) > 0.85  # the stem's speech is heard
    assert np.all(out.audio.voice >= mix_voice)  # never less than the mix alone


def test_chunks_without_a_stem_or_audio_are_left_alone(detector: VoiceDetector) -> None:
    speech = _speech_signal()
    unseparated = _chunk(speech, detector.probabilities(speech))
    no_audio = _chunk(None, None)
    no_voice = _chunk(speech, None)
    chunks = [unseparated, no_audio, no_voice]
    assert list(attach_separated_voice(chunks, _Stems(None), detector)) == chunks
    assert list(attach_separated_voice([no_audio, no_voice], _Stems(speech), detector)) == [
        no_audio,
        no_voice,
    ]


# ---- the pipeline --------------------------------------------------------------------------------


def test_speech_in_the_stem_reaches_the_stored_features(
    fake_demucs: Path, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    film = _clip(tmp_path, LOUD)
    plain = _speech(film, tmp_path / "plain", None)
    with caplog.at_level(logging.INFO, logger="filmanalyser"):
        separated = _speech(film, tmp_path / "separated", fake_demucs)
    assert np.all(plain < 0.1)  # the chord alone is not speech
    assert np.all(separated > 0.5)  # the stem's speech is
    assert len(_runs(tmp_path)) == 1  # three chunks, one batch, one run
    events = [json.loads(r.getMessage()) for r in caplog.records]
    batch = [e for e in events if e.get("event") == "separation_batch"]
    assert batch == [{"event": "separation_batch", "first": 0, "chunks": 3, "separated": 3}]


def test_a_quiet_background_is_not_separated(fake_demucs: Path, tmp_path: Path) -> None:
    film = _clip(tmp_path, QUIET)
    _speech(film, tmp_path / "store", fake_demucs)
    assert _runs(tmp_path) == []  # nothing was loud enough: the tool never ran


def test_a_five_one_film_uses_its_centre_channel_instead(
    fake_demucs: Path, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    film = _clip(tmp_path, LOUD, layout="5.1")
    with caplog.at_level(logging.INFO, logger="filmanalyser"):
        _speech(film, tmp_path / "store", fake_demucs)
    assert _runs(tmp_path) == []
    assert '"separation_skipped"' in caplog.text
