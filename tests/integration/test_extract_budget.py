"""Performance budget (Improvement 6, DECISIONS #57): extraction must keep up with the film. Each
chunk may take at most EXTRACT_BUDGET_FRACTION of its own duration to extract. The budget is
relative to film time, so it means the same on a laptop and on a CI runner, and it leaves large
headroom: a slowdown of that size is a regression, not noise."""

from pathlib import Path
from time import perf_counter

from filmanalyser.core.config import EXTRACT_BUDGET_FRACTION, Config
from filmanalyser.extractors.registry import discover
from filmanalyser.media.audio import audio_stream
from filmanalyser.pipeline.runner import chunk_stream, extract_chunk
from tests.fixtures.make_synthetic import make_clip

CONFIG = Config(chunk_seconds=30.0, overlap_seconds=1.0, analysis_fps=12.0, frame_width=160)


def test_every_chunk_is_extracted_within_the_time_budget(tmp_path: Path) -> None:
    film = make_clip(tmp_path / "budget.mp4", seconds=120, size=(320, 180), fps=12)
    registry = discover()
    # the chunks a real run extracts: audio and voice included, decoded before any timing starts
    chunks = list(chunk_stream(film, CONFIG, 0, audio_stream(film)))
    assert len(chunks) == 4
    for chunk in chunks:
        began = perf_counter()
        extract_chunk(registry, chunk)
        spent = perf_counter() - began
        allowed = EXTRACT_BUDGET_FRACTION * chunk.duration_s
        assert spent <= allowed, f"chunk {chunk.index}: {spent:.3f} s > {allowed:.3f} s"
