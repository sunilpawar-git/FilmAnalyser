"""Real footage (Improvement 3, DECISIONS #53, #54): kill a run mid-clip, resume it, and require the
stored features to equal an uninterrupted run's. The clip is outside the repo and named by an
environment variable. It is deselected from `make check` and run by `make real-clip`; it never
skips: a missing or unreadable clip fails the test."""

import os
from pathlib import Path

import pytest

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
