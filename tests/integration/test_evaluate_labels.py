"""The evaluator on real decodes: speech on the TTS fixture, cuts on a clip with known cuts, and
the whole-film loudness stitched across segments (DECISIONS #70)."""

import subprocess
from pathlib import Path

import pytest

import evaluate_labels as evaluate
from evaluate_labels import cut_predictions, film_loudness, score_cuts, window_predictions
from filmanalyser.extractors.speech_music import SPEECH
from tests.fixtures.make_synthetic import cut_times, make_av_clip, make_cut_clip

SPEECH_WAV = Path(__file__).resolve().parents[1] / "fixtures" / "speech_16k.wav"
SCENES = [("red", 3.0), ("green", 2.5), ("blue", 4.0), ("white", 3.5)]
TONE = "0.5*sin(2*PI*440*t)*between(t\\,2\\,4)"


def _speech_clip(out: Path) -> Path:
    """The TTS fixture as the soundtrack of a short picture (QuickTime, PCM, as in the fixtures)."""
    subprocess.run(
        [
            "ffmpeg", "-v", "error", "-y",
            "-f", "lavfi", "-i", "color=c=black:s=160x90:r=12:d=6",
            "-i", str(SPEECH_WAV), "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
            "-c:a", "pcm_s16le", "-shortest", "-f", "mov", "--", str(out),
        ],
        check=True,
    )  # fmt: skip
    return out


def test_speech_is_found_where_the_labels_say_speech(tmp_path: Path) -> None:
    film = _speech_clip(tmp_path / "speech.mp4")
    times, predicted = window_predictions(film)
    labels = evaluate.parse_labels("speech 0 5.5\n")
    score = evaluate.score_kind(labels, "speech", times, predicted == SPEECH)
    assert score.precision is not None and score.precision > 0.8
    assert score.recall is not None and score.recall > 0.8


def test_cuts_are_found_where_the_clip_has_them(tmp_path: Path) -> None:
    film = make_cut_clip(tmp_path / "cuts.mp4", SCENES, fps=12)
    truth = tuple(cut_times(SCENES, 12))
    score = score_cuts(truth, cut_predictions(film), tolerance=1 / 12)
    assert score.precision == 1.0 and score.recall == 1.0


def test_whole_film_loudness_is_the_same_whichever_segment_size_is_used(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    film = make_av_clip(tmp_path / "tone.mp4", 6.0, TONE)
    single, single_peak = film_loudness(film)
    monkeypatch.setattr(evaluate, "SEGMENT_S", 1.0)  # six segments: the seams must not matter
    stitched, stitched_peak = film_loudness(film)
    assert single is not None and stitched is not None
    assert stitched == pytest.approx(single, abs=0.01)
    assert stitched_peak == pytest.approx(single_peak, abs=0.01)
