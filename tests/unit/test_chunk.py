"""Chunk contract and the frame-index maths that define overlap (pure, no I/O)."""

import dataclasses

import numpy as np
import pytest

from filmanalyser.core.chunk import Chunk, expected_chunks, frames_for, span_for
from filmanalyser.core.errors import InputError


def _frames(count: int, h: int = 2, w: int = 2) -> np.ndarray:
    return np.zeros((count, h, w, 3), dtype=np.uint8)


def test_chunk_exposes_core_and_context() -> None:
    chunk = Chunk(index=1, start_s=10.0, end_s=20.0, fps=2.0, frames=_frames(24), context_frames=4)
    assert len(chunk.core) == 20
    assert chunk.first_frame_s == 8.0  # 4 context frames at 2 fps = 2 s of overlap
    assert chunk.duration_s == 10.0


def test_chunk_frames_are_read_only() -> None:
    chunk = Chunk(index=0, start_s=0.0, end_s=1.0, fps=2.0, frames=_frames(2), context_frames=0)
    with pytest.raises(ValueError, match="read-only"):
        chunk.frames[0, 0, 0, 0] = 1


def test_chunk_does_not_freeze_the_callers_array() -> None:
    source = _frames(2)
    Chunk(index=0, start_s=0.0, end_s=1.0, fps=2.0, frames=source, context_frames=0)
    source[0, 0, 0, 0] = 1  # the original stays writable; only the chunk's view is locked


def test_chunk_is_immutable() -> None:
    chunk = Chunk(index=0, start_s=0.0, end_s=1.0, fps=2.0, frames=_frames(2), context_frames=0)
    with pytest.raises(dataclasses.FrozenInstanceError):
        chunk.index = 5  # type: ignore[misc]


@pytest.mark.parametrize(
    "frames",
    [np.zeros((2, 2, 3), np.uint8), np.zeros((2, 2, 2, 4), np.uint8), np.zeros((2, 2, 2, 3))],
    ids=["wrong ndim", "wrong channels", "wrong dtype"],
)
def test_chunk_rejects_bad_frame_arrays(frames: np.ndarray) -> None:
    with pytest.raises(InputError, match="frames"):
        Chunk(index=0, start_s=0.0, end_s=1.0, fps=2.0, frames=frames, context_frames=0)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"index": -1},
        {"fps": 0.0},
        {"end_s": 0.0},  # end must be after start
        {"context_frames": 3},  # more context than frames
        {"context_frames": -1},
    ],
)
def test_chunk_rejects_bad_fields(kwargs: dict[str, float]) -> None:
    fields: dict[str, float] = {
        "index": 0,
        "start_s": 0.0,
        "end_s": 1.0,
        "fps": 2.0,
        "context_frames": 0,
    }
    with pytest.raises(InputError):
        Chunk(frames=_frames(2), **{**fields, **kwargs})  # type: ignore[arg-type]


def test_first_chunk_has_no_context() -> None:
    span = span_for(0, per_chunk=100, overlap=20)
    assert (span.context_start, span.core_start, span.core_end) == (0, 0, 100)
    assert span.context_len == 0


def test_later_chunks_reach_back_by_the_overlap() -> None:
    span = span_for(3, per_chunk=100, overlap=20)
    assert (span.context_start, span.core_start, span.core_end) == (280, 300, 400)
    assert span.context_len == 20


def test_zero_overlap_means_no_context() -> None:
    assert span_for(2, per_chunk=10, overlap=0).context_len == 0


@pytest.mark.parametrize(("total", "expected"), [(0, 0), (1, 1), (100, 1), (101, 2), (1200, 12)])
def test_expected_chunks_is_a_ceiling_division(total: int, expected: int) -> None:
    assert expected_chunks(total, per_chunk=100) == expected


@pytest.mark.parametrize(
    ("seconds", "fps", "frames"), [(60.0, 12.0, 720), (2.0, 12.0, 24), (0.01, 10.0, 1)]
)
def test_frames_for_rounds_and_never_returns_zero(seconds: float, fps: float, frames: int) -> None:
    assert frames_for(seconds, fps) == frames


@pytest.mark.parametrize(("per_chunk", "overlap"), [(0, 0), (-1, 0), (10, -1), (10, 10), (10, 11)])
def test_span_rejects_impossible_geometry(per_chunk: int, overlap: int) -> None:
    with pytest.raises(InputError):
        span_for(0, per_chunk=per_chunk, overlap=overlap)
