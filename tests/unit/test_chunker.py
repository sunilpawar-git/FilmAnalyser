"""The chunker groups a frame stream into overlapping chunks. Frames here are 1x1 pixels that
encode their own index, so overlap and ordering can be checked exactly. Includes hypothesis
property tests for the overlap maths (Improvement 4)."""

from collections.abc import Iterator

import numpy as np
import pytest
from hypothesis import given
from hypothesis import strategies as st

from filmanalyser.core.chunk import Chunk, expected_chunks
from filmanalyser.core.config import Config
from filmanalyser.media.chunker import chunk_frames

SHAPE = (1, 1)


def _stream(total: int) -> Iterator[np.ndarray]:
    for i in range(total):
        yield np.array([[[i % 256, (i // 256) % 256, i // 65536]]], dtype=np.uint8)


def _index(frame: np.ndarray) -> int:
    r, g, b = (int(v) for v in frame[0, 0])
    return r + 256 * g + 65536 * b


def _ids(frames: np.ndarray) -> list[int]:
    return [_index(f) for f in frames]


def _run(total: int, per_chunk: int, overlap: int, fps: float = 10.0) -> list[Chunk]:
    config = Config(chunk_seconds=per_chunk / fps, overlap_seconds=overlap / fps, analysis_fps=fps)
    return list(chunk_frames(_stream(total), config, SHAPE))


def test_exact_multiple_gives_equal_chunks() -> None:
    chunks = _run(total=1200, per_chunk=100, overlap=10)
    assert len(chunks) == 12
    assert all(len(c.core) == 100 for c in chunks)
    assert [c.duration_s for c in chunks] == [10.0] * 12


def test_remainder_becomes_a_short_final_chunk() -> None:
    chunks = _run(total=250, per_chunk=100, overlap=10)
    assert [len(c.core) for c in chunks] == [100, 100, 50]
    assert chunks[-1].end_s == 25.0


def test_core_windows_partition_the_stream() -> None:
    chunks = _run(total=250, per_chunk=100, overlap=10)
    assert [i for c in chunks for i in _ids(c.core)] == list(range(250))


def test_context_repeats_the_previous_tail_exactly() -> None:
    chunks = _run(total=300, per_chunk=100, overlap=10)
    assert chunks[0].context_frames == 0
    for prev, cur in zip(chunks, chunks[1:], strict=False):
        assert cur.context_frames == 10
        assert _ids(cur.frames[:10]) == _ids(prev.core[-10:])
        assert cur.first_frame_s == pytest.approx(cur.start_s - 1.0)


def test_empty_stream_yields_nothing() -> None:
    assert _run(total=0, per_chunk=100, overlap=10) == []


def test_chunks_are_numbered_and_timed_from_zero() -> None:
    chunks = _run(total=300, per_chunk=100, overlap=10)
    assert [c.index for c in chunks] == [0, 1, 2]
    assert [(c.start_s, c.end_s) for c in chunks] == [(0.0, 10.0), (10.0, 20.0), (20.0, 30.0)]


def test_chunking_is_lazy() -> None:
    pulled = 0

    def counting() -> Iterator[np.ndarray]:
        nonlocal pulled
        for frame in _stream(1000):
            pulled += 1
            yield frame

    config = Config(chunk_seconds=10.0, overlap_seconds=1.0, analysis_fps=10.0)
    first = next(chunk_frames(counting(), config, SHAPE))
    assert len(first.core) == 100
    assert pulled == 100  # nothing read ahead


def test_frame_shape_mismatch_is_rejected() -> None:
    config = Config(chunk_seconds=1.0, overlap_seconds=0.0, analysis_fps=10.0)
    bad = iter([np.zeros((2, 2, 3), np.uint8)])
    with pytest.raises(ValueError, match="shape"):
        next(chunk_frames(bad, config, SHAPE))


@given(
    total=st.integers(0, 600),
    per_chunk=st.integers(1, 80),
    overlap_pct=st.integers(0, 99),
)
def test_property_chunks_partition_and_overlap_exactly(
    total: int, per_chunk: int, overlap_pct: int
) -> None:
    overlap = per_chunk * overlap_pct // 100
    chunks = _run(total, per_chunk, overlap)
    assert len(chunks) == expected_chunks(total, per_chunk)
    assert [i for c in chunks for i in _ids(c.core)] == list(range(total))
    for prev, cur in zip(chunks, chunks[1:], strict=False):
        wanted = min(overlap, len(prev.core)) if overlap else 0
        assert cur.context_frames == wanted == overlap
        assert _ids(cur.frames[: cur.context_frames]) == _ids(prev.core[len(prev.core) - wanted :])
    assert all(c.start_s < c.end_s for c in chunks)
    assert all(a.end_s == b.start_s for a, b in zip(chunks, chunks[1:], strict=False))


@given(total=st.integers(1, 400), per_chunk=st.integers(1, 50))
def test_property_only_the_last_chunk_may_be_short(total: int, per_chunk: int) -> None:
    sizes = [len(c.core) for c in _run(total, per_chunk, 0)]
    assert all(s == per_chunk for s in sizes[:-1])
    assert 1 <= sizes[-1] <= per_chunk
    assert sum(sizes) == total


def _stream_from(start: int, total: int) -> Iterator[np.ndarray]:
    for frame in _stream(total):
        if _index(frame) >= start:
            yield frame


@pytest.mark.parametrize("first", [1, 2, 3])
def test_a_resumed_stream_reproduces_the_later_chunks_exactly(first: int) -> None:
    """The stream a resumed run decodes starts at the context of chunk `first`, not at frame 0."""
    config = Config(chunk_seconds=10.0, overlap_seconds=1.0, analysis_fps=10.0)
    full = list(chunk_frames(_stream(380), config, SHAPE))
    start = first * 100 - 10
    resumed = list(chunk_frames(_stream_from(start, 380), config, SHAPE, first_index=first))
    assert [c.index for c in resumed] == [c.index for c in full[first:]]
    for got, want in zip(resumed, full[first:], strict=True):
        assert (got.start_s, got.end_s, got.context_frames) == (
            want.start_s,
            want.end_s,
            want.context_frames,
        )
        assert _ids(got.frames) == _ids(want.frames)


def test_a_resumed_stream_that_ends_inside_the_context_yields_nothing() -> None:
    config = Config(chunk_seconds=10.0, overlap_seconds=1.0, analysis_fps=10.0)
    assert list(chunk_frames(_stream_from(190, 195), config, SHAPE, first_index=2)) == []
