"""Chunk: the unit of work every extractor receives, and the frame-index maths behind overlap.

A chunk "owns" a core window [start_s, end_s) of the film. Its `frames` also hold up to
`context_frames` leading frames copied from the end of the previous chunk (the overlap), so an
extractor can carry state across a boundary; it emits features only for the core window.
Frames are downscaled RGB (uint8, shape (n, height, width, 3)) at the analysis frame rate, with
film time starting at zero (container offsets are removed by the decoder).
"""

from dataclasses import dataclass
from typing import Any

import numpy as np
import numpy.typing as npt

from filmanalyser.core.errors import InputError

Frames = npt.NDArray[np.uint8]
Samples = npt.NDArray[np.float32]
MAX_AUDIO_CHANNELS = 6  # 5.1 at most: BS.1770's surround weighting needs the channel order


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


def _locked(array: npt.NDArray[Any]) -> npt.NDArray[Any]:
    """A read-only view: the chunk's data cannot change after it is built (the caller's stays
    writable)."""
    view = array.view()
    view.flags.writeable = False
    return view


@dataclass(frozen=True, eq=False)  # eq off: array equality is ambiguous; identity is the identity
class Audio:
    """PCM for the same window as a chunk's frames (it starts at the first frame's film time).

    `samples` is (count, channels), float32 in [-1, 1], one to six channels, at `rate` Hz. `voice`,
    when the pipeline has run the voice detector, holds one speech probability (0..1) per
    consecutive block of samples, starting at the window's first sample.
    """

    rate: int
    start_s: float
    samples: Samples
    voice: npt.NDArray[np.float32] | None = None

    def __post_init__(self) -> None:
        samples = self.samples
        if self.rate <= 0 or samples.ndim != 2 or samples.dtype != np.float32:
            raise _bad("audio")
        if not 1 <= samples.shape[1] <= MAX_AUDIO_CHANNELS or len(samples) == 0:
            raise _bad("audio")
        if not np.isfinite(samples).all():
            raise _bad("audio")
        object.__setattr__(self, "samples", _locked(samples))
        if self.voice is not None:
            if self.voice.ndim != 1 or not np.isfinite(self.voice).all():
                raise _bad("voice")
            object.__setattr__(self, "voice", _locked(self.voice))


@dataclass(frozen=True, eq=False)  # eq off: array equality is ambiguous; identity is the identity
class Chunk:
    index: int
    start_s: float
    end_s: float
    fps: float
    frames: Frames
    context_frames: int
    audio: Audio | None = None

    def __post_init__(self) -> None:
        if self.index < 0 or self.fps <= 0 or self.end_s <= self.start_s:
            raise _bad("chunk")
        frames = self.frames
        if frames.ndim != 4 or frames.shape[3] != 3 or frames.dtype != np.uint8:
            raise _bad("frames")
        if not 0 <= self.context_frames <= len(frames):
            raise _bad("context_frames")
        object.__setattr__(self, "frames", _locked(frames))
        if self.audio is not None and abs(self.audio.start_s - self.first_frame_s) > 1e-9:
            raise _bad("audio")  # the audio must cover the same window as the frames

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

    @property
    def audio_core_offset(self) -> int:
        """Sample index (in `audio.samples`) where the core window starts: the context's length in
        seconds, at the audio rate. Needs audio; 0 without context."""
        if self.audio is None:
            raise _bad("audio")
        return round(self.context_frames * self.audio.rate / self.fps)

    @property
    def core_audio(self) -> Samples:
        """The samples this chunk owns (everything after the leading context)."""
        if self.audio is None:
            raise _bad("audio")
        return self.audio.samples[self.audio_core_offset :]
