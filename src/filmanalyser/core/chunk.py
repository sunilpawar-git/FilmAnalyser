"""Chunk: the unit of work every extractor receives, and the frame-index maths behind overlap.

A chunk "owns" a core window [start_s, end_s) of the film. Its `frames` also hold up to
`context_frames` leading frames copied from the end of the previous chunk (the overlap), so an
extractor can carry state across a boundary; it emits features only for the core window.
Frames are downscaled RGB (uint8, shape (n, height, width, 3)) at the analysis frame rate, with
film time starting at zero (container offsets are removed by the decoder).
"""

from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

from filmanalyser.core.errors import InputError

Frames = npt.NDArray[np.uint8]


def _bad(name: str) -> InputError:
    return InputError(key="error.input.bad_setting", name=name)


@dataclass(frozen=True)
class ChunkSpan:
    """Frame indices (into the whole film) of one chunk; the core window is half-open."""

    index: int
    context_start: int
    core_start: int
    core_end: int

    @property
    def context_len(self) -> int:
        return self.core_start - self.context_start


def span_for(index: int, per_chunk: int, overlap: int) -> ChunkSpan:
    """The SSOT for overlap maths: chunk `index` owns `per_chunk` frames and reaches back
    `overlap` frames (none for the first chunk)."""
    if per_chunk < 1 or not 0 <= overlap < per_chunk or index < 0:
        raise _bad("chunk_geometry")
    core_start = index * per_chunk
    return ChunkSpan(index, max(0, core_start - overlap), core_start, core_start + per_chunk)


def expected_chunks(total_frames: int, per_chunk: int) -> int:
    """How many chunks a stream of `total_frames` frames is cut into (ceiling division)."""
    return -(-total_frames // per_chunk)


def frames_for(seconds: float, fps: float) -> int:
    """Whole frames in a duration, never fewer than one."""
    return max(1, round(seconds * fps))


@dataclass(frozen=True, eq=False)  # eq off: array equality is ambiguous; identity is the identity
class Chunk:
    index: int
    start_s: float
    end_s: float
    fps: float
    frames: Frames
    context_frames: int

    def __post_init__(self) -> None:
        if self.index < 0 or self.fps <= 0 or self.end_s <= self.start_s:
            raise _bad("chunk")
        frames = self.frames
        if frames.ndim != 4 or frames.shape[3] != 3 or frames.dtype != np.uint8:
            raise _bad("frames")
        if not 0 <= self.context_frames <= len(frames):
            raise _bad("context_frames")
        locked = frames.view()  # lock our view only; the caller's array stays writable
        locked.flags.writeable = False
        object.__setattr__(self, "frames", locked)

    @property
    def core(self) -> Frames:
        """The frames this chunk owns (everything after the leading context)."""
        return self.frames[self.context_frames :]

    @property
    def first_frame_s(self) -> float:
        """Film time of `frames[0]` (the start of the overlap)."""
        return self.start_s - self.context_frames / self.fps

    @property
    def duration_s(self) -> float:
        return self.end_s - self.start_s
