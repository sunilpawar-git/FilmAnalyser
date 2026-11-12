"""Real footage (Improvement 3, DECISIONS #53, #54): kill a run mid-clip, resume it, and require the
stored features to equal an uninterrupted run's. The clip is outside the repo and named by an
environment variable. It is deselected from `make check` and run by `make real-clip`; it never
skips: a missing or unreadable clip fails the test."""

import os
from pathlib import Path

import numpy as np
import pytest

from filmanalyser.core.config import LOUDNESS_ABS_GATE_LUFS
from filmanalyser.extractors.speech_music import FEATURES
from filmanalyser.pipeline.runner import analyse
from tests.integration._kill import run_until_killed
from tests.integration._resume_worker import REAL

pytestmark = pytest.mark.real_clip

ENV = "FILMANALYSER_REAL_CLIP"


def _clip() -> Path:
    raw = os.environ.get(ENV, "")
    path = Path(raw)
    if not raw or not path.is_file():
        pytest.fail(f"{ENV} must name a readable clip outside the repo (see make real-clip)")
    return path


def test_kill_mid_clip_then_resume_equals_an_uninterrupted_run(tmp_path: Path) -> None:
    clip = _clip()
    expected = analyse(clip, tmp_path / "reference", REAL).read_columns()
    run_until_killed(clip, tmp_path / "out", gate=3, profile="real")
    resumed = analyse(clip, tmp_path / "out", REAL).read_columns()
    assert set(resumed) == set(expected)
    for name in expected:
        assert (resumed[name] == expected[name]).all(), f"column {name} differs after resume"


def test_real_clip_audio_features_are_well_formed(tmp_path: Path) -> None:
    """Phase 5 on real footage: every chunk has a finite loudness inside the BS.1770 range, and its
    speech, music, silence and other ratios sum to one (the classifier labels every core window)."""
    columns = analyse(_clip(), tmp_path / "out", REAL).read_columns()
    lufs = np.asarray(columns["loudness.integrated_lufs"], dtype=np.float64)
    assert np.isfinite(lufs).all()
    assert ((lufs >= LOUDNESS_ABS_GATE_LUFS) & (lufs <= 0.0)).all()
    peaks = np.asarray(columns["loudness.peak_dbfs"], dtype=np.float64)
    assert np.isfinite(peaks).all() and (peaks <= 0.0).all()
    ratios = sum(np.asarray(columns[f"speech_music.{name}"], dtype=np.float64) for name in FEATURES)
    assert np.allclose(ratios, 1.0, atol=1e-9)
