"""Shot cuts: hard cuts between consecutive frames, from soft colour histograms (DECISIONS #51).

Each frame becomes, per colour channel, a histogram of HIST_BINS soft bins (a pixel's weight is
split between its two nearest bins, so a slow change moves the histogram smoothly). The distance
between two frames is the largest per-channel change (0..1). A cut is a distance above CUT_DISTANCE.

Cut ownership (DECISIONS #55): a cut belongs to the chunk whose core holds the frame where the new
scene starts. That frame is compared with its predecessor, which is in the overlap for every chunk
after the first, so a boundary cut is found once and never twice.
"""

from collections.abc import Mapping
from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

from filmanalyser.core.chunk import Chunk, Frames
from filmanalyser.core.config import CUT_DISTANCE, HIST_BINS
from filmanalyser.core.features import SHOT_CUTS

NAME = SHOT_CUTS
VERSION = 1
FEATURES = ("cuts", "max_diff")
_CHANNELS = 3


def _histograms(frames: Frames) -> npt.NDArray[np.float64]:
    """Shape (frames, channels, bins): each channel's soft histogram, summing to 1 per channel."""
    scale = (HIST_BINS - 1) / 255.0
    out = np.empty((len(frames), _CHANNELS, HIST_BINS))
    for index, frame in enumerate(frames):
        pixels = frame.reshape(-1, _CHANNELS).astype(np.float64) * scale
        low = np.floor(pixels).astype(np.intp)
        high = np.minimum(low + 1, HIST_BINS - 1)
        upper = pixels - low
        for channel in range(_CHANNELS):
            out[index, channel] = np.bincount(
                low[:, channel], weights=1.0 - upper[:, channel], minlength=HIST_BINS
            ) + np.bincount(high[:, channel], weights=upper[:, channel], minlength=HIST_BINS)
        out[index] /= len(pixels)
    return out


def frame_distances(frames: Frames) -> npt.NDArray[np.float64]:
    """Distance between each frame and the next: element k compares frame k with frame k + 1."""
    hist = _histograms(frames)
    per_channel = 0.5 * np.abs(np.diff(hist, axis=0)).sum(axis=2)
    return np.asarray(per_channel.max(axis=1), dtype=np.float64)


def cut_positions(frames: Frames, context_frames: int) -> tuple[int, ...]:
    """Indices (into `frames`) of the frames where a cut starts, counting only frames at or after
    `context_frames` (the first frame has no predecessor unless it is a context frame)."""
    distances = frame_distances(frames)
    starts = np.flatnonzero(distances > CUT_DISTANCE) + 1
    first = max(1, context_frames)
    return tuple(int(index) for index in starts if index >= first)


@dataclass(frozen=True)
class ShotCuts:
    name: str = NAME
    version: int = VERSION
    features: tuple[str, ...] = FEATURES
    needs_audio: bool = False

    def extract(self, chunk: Chunk) -> Mapping[str, float]:
        distances = frame_distances(chunk.frames)
        core = distances[max(1, chunk.context_frames) - 1 :]  # distances that end on a core frame
        cuts = int(np.count_nonzero(core > CUT_DISTANCE))
        return {"cuts": float(cuts), "max_diff": float(np.max(core)) if core.size else 0.0}


EXTRACTOR = ShotCuts()
