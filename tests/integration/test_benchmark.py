"""Nightly benchmark (a Phase 4 deliverable): record how fast a long film is analysed and how much
memory it takes. It prints one `BENCH` record that the nightly workflow copies into the job summary.
It asserts only that the record is well-formed, never an absolute speed: CI runners differ, and the
gates that matter (the per-chunk budget, the memory plateau) are tested elsewhere."""

import math
from pathlib import Path
from time import perf_counter

import pytest

from filmanalyser.core.config import Config
from filmanalyser.media.telemetry import peak_rss_mb
from filmanalyser.pipeline.runner import analyse
from tests.fixtures.make_synthetic import make_clip

pytestmark = pytest.mark.slow
FILM_SECONDS = 600  # ten minutes: long enough to reach the steady state, short enough for nightly


def test_long_film_throughput_and_memory_are_recorded(tmp_path: Path) -> None:
    film = make_clip(tmp_path / "bench.mp4", seconds=FILM_SECONDS, size=(320, 180), fps=12)
    config = Config()  # the product defaults: 60 s chunks, 12 fps, 160 px
    began = perf_counter()
    store = analyse(film, tmp_path / "out", config)
    wall = perf_counter() - began
    chunks = store.next_chunk
    throughput = FILM_SECONDS / wall  # film seconds analysed per wall-clock second
    print(
        f"\nBENCH film_s={FILM_SECONDS} chunks={chunks} wall_s={wall:.1f} "
        f"film_s_per_wall_s={throughput:.1f} peak_rss_mb={peak_rss_mb():.0f}"
    )
    assert store.complete
    assert chunks == math.ceil(FILM_SECONDS / config.chunk_seconds)
    assert math.isfinite(throughput) and throughput > 0
