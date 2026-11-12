"""RSS flatness: a film many times longer must not raise peak RSS. Each film is decoded in its own
process, so the measurement is the film's own peak, not a leftover from an earlier test. The 40x
variant is `slow` and runs nightly (EXECUTION_PLAN: long-film memory test)."""

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from filmanalyser.core.config import Config
from tests.architecture._scan import REPO
from tests.fixtures.make_synthetic import concat_clip, make_clip

CHUNK_SECONDS = 10.0
GROWTH_ALLOWED = 0.05  # allowed rise after the last checkpoint
SLACK_MB = 8.0  # ...plus allocator noise
FILM_SECONDS = 120
FACTORS = (10, pytest.param(40, marks=pytest.mark.slow, id="40x"))


def _decode_in_fresh_process(film: Path) -> dict[str, Any]:
    done = subprocess.run(
        [sys.executable, "-m", "tests.integration._decode_worker", str(film), str(CHUNK_SECONDS)],
        check=True,
        capture_output=True,
        text=True,
        cwd=REPO,  # the worker is imported as `tests.integration...` from the repo root
    )
    result: dict[str, Any] = json.loads(done.stdout.splitlines()[-1])
    return result


@pytest.fixture(scope="module", params=FACTORS)
def measurements(
    request: pytest.FixtureRequest, tmp_path_factory: pytest.TempPathFactory
) -> tuple[int, dict[str, Any], dict[str, Any]]:
    factor = int(request.param if isinstance(request.param, int) else request.param[0])
    work = tmp_path_factory.mktemp("memory")
    short = make_clip(work / "short.mp4", seconds=FILM_SECONDS)
    long = concat_clip(short, work / f"long{factor}.mp4", times=factor)
    return factor, _decode_in_fresh_process(short), _decode_in_fresh_process(long)


def test_the_long_film_really_is_that_much_longer(
    measurements: tuple[int, dict[str, Any], dict[str, Any]],
) -> None:
    factor, short, long = measurements
    assert short["chunks"] == 12
    assert long["chunks"] == pytest.approx(short["chunks"] * factor, abs=factor)
    assert long["frames"] == pytest.approx(short["frames"] * factor, rel=0.02)


def test_peak_rss_stops_rising_once_warm(
    measurements: tuple[int, dict[str, Any], dict[str, Any]],
) -> None:
    """Allocators warm up at different speeds (macOS CI needed ~64 chunks to plateau, a laptop
    4), so a short-vs-long comparison measures warm-up, not growth. Flatness is therefore: after
    the largest checkpoint, the remaining chunks add no memory. A leak adds about one chunk (~3 MB
    here, ~31 MB in production) per chunk and fails this by a mile."""
    _factor, short, long = measurements
    curve: dict[str, float] = long["curve"]
    checkpoint = curve[str(max(int(k) for k in curve))]
    print(f"\nRSS flatness: {short['curve']} vs {curve}; final {long['peak_rss_mb']:.1f} MB")
    assert long["peak_rss_mb"] <= checkpoint * (1 + GROWTH_ALLOWED) + SLACK_MB, curve


def test_peak_rss_is_far_below_the_budget(
    measurements: tuple[int, dict[str, Any], dict[str, Any]],
) -> None:
    assert measurements[2]["peak_rss_mb"] < Config().ram_budget_mb / 4
