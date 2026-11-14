"""Golden output on short clips (ACCEPTANCE, Quality gates): the stored features of two fixed
synthetic clips are pinned to `tests/golden/short_clip.json`. The clips are made by the local ffmpeg
(the encoder differs between versions), so each column has a tolerance; a change to an extractor
that moves a value beyond it fails here and must be a reviewed change to the golden file.

To refresh after a deliberate change: `uv run python -m tests.integration.test_golden_clip`
prints the new JSON; review the diff before committing it."""

import json
import sys
import tempfile
from pathlib import Path

import numpy as np
import pytest

from filmanalyser.core.config import Config
from filmanalyser.pipeline.runner import analyse
from tests.fixtures.make_synthetic import make_av_clip, make_cut_clip

GOLDEN = Path(__file__).resolve().parents[1] / "golden" / "short_clip.json"
CONFIG = Config(chunk_seconds=2.0, overlap_seconds=0.5, analysis_fps=12.0, frame_width=64)
TONE = "0.5*sin(2*PI*440*t)*between(t\\,2\\,4)"
LEVEL_TOLERANCE = 1.5  # dB: the ring-out of the tone's abrupt stop depends on the encoder a little
KEEP = ("loudness.", "speech_music.", "shot_cuts.cuts", "chunk_index", "start_s", "end_s")


def _columns(film: Path, root: Path, *, only: tuple[str, ...] = ()) -> dict[str, list[float]]:
    stored = analyse(film, root, CONFIG).read_columns()
    return {
        name: [round(float(x), 3) for x in values]
        for name, values in stored.items()
        if not only or name.startswith(only)
    }


def _clips(root: Path) -> dict[str, dict[str, list[float]]]:
    cut = make_cut_clip(root / "cut.mp4", [("red", 2.0), ("blue", 2.0)], fps=12)
    tone = make_av_clip(root / "tone.mp4", 6.0, TONE)
    return {
        "cut": _columns(cut, root / "cut"),  # picture only: every colour and cut column
        "tone": _columns(tone, root / "tone", only=KEEP),  # sound columns (the ramp picture varies)
    }


@pytest.fixture(scope="module")
def current(tmp_path_factory: pytest.TempPathFactory) -> dict[str, dict[str, list[float]]]:
    return _clips(tmp_path_factory.mktemp("golden"))


@pytest.mark.parametrize("clip", ["cut", "tone"])
def test_the_stored_features_match_the_golden_file(
    current: dict[str, dict[str, list[float]]], clip: str
) -> None:
    golden = json.loads(GOLDEN.read_text(encoding="utf-8"))
    assert sorted(current[clip]) == sorted(golden[clip])  # the same columns, no more, no less
    for name, expected in golden[clip].items():
        tolerance = LEVEL_TOLERANCE if name.startswith("loudness.") else 0.05
        np.testing.assert_allclose(current[clip][name], expected, atol=tolerance, err_msg=name)


if __name__ == "__main__":  # pragma: no cover
    with tempfile.TemporaryDirectory() as folder:
        json.dump(_clips(Path(folder)), sys.stdout, indent=1)
