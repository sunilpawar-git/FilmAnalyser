"""RSS flatness: a film 10x longer must not raise peak RSS. Each film is decoded in its own
process, so the measurement is the film's own peak, not a leftover from an earlier test."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from filmanalyser.core.config import Config
from tests.architecture._scan import REPO
from tests.fixtures.make_synthetic import concat_clip, make_clip

CHUNK_SECONDS = 10.0
GROWTH_ALLOWED = 0.10  # peak RSS of the 10x film may exceed the 1x film by at most 10 %
SLACK_MB = 8.0  # ...plus allocator noise
FILM_SECONDS = 120
FACTOR = 10


def _decode_in_fresh_process(film: Path) -> dict[str, float]:
    done = subprocess.run(
        [sys.executable, "-m", "tests.integration._decode_worker", str(film), str(CHUNK_SECONDS)],
        check=True,
        capture_output=True,
        text=True,
        cwd=REPO,  # the worker is imported as `tests.integration...` from the repo root
    )
    result: dict[str, float] = json.loads(done.stdout.splitlines()[-1])
    return result


@pytest.fixture(scope="module")
def measurements(
    tmp_path_factory: pytest.TempPathFactory,
) -> tuple[dict[str, float], dict[str, float]]:
    work = tmp_path_factory.mktemp("memory")
    short = make_clip(work / "short.mp4", seconds=FILM_SECONDS)
    long = concat_clip(short, work / "long.mp4", times=FACTOR)
    return _decode_in_fresh_process(short), _decode_in_fresh_process(long)


def test_the_long_film_really_is_ten_times_longer(
    measurements: tuple[dict[str, float], dict[str, float]],
) -> None:
    short, long = measurements
    assert short["chunks"] == 12
    assert long["chunks"] == pytest.approx(short["chunks"] * FACTOR, abs=FACTOR)
    assert long["frames"] == pytest.approx(short["frames"] * FACTOR, rel=0.02)


def test_peak_rss_does_not_grow_with_film_length(
    measurements: tuple[dict[str, float], dict[str, float]],
) -> None:
    short, long = measurements
    print(
        f"\nRSS flatness: {short['chunks']:.0f} chunks -> {short['peak_rss_mb']:.1f} MB; "
        f"{long['chunks']:.0f} chunks -> {long['peak_rss_mb']:.1f} MB"
    )
    assert long["peak_rss_mb"] <= short["peak_rss_mb"] * (1 + GROWTH_ALLOWED) + SLACK_MB


def test_peak_rss_is_far_below_the_budget(
    measurements: tuple[dict[str, float], dict[str, float]],
) -> None:
    assert measurements[1]["peak_rss_mb"] < Config().ram_budget_mb / 4
