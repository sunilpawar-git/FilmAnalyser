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
from filmanalyser.core.config import (
    CUT_DISTANCE,
    CUT_MERGE_FRAMES,
    GRADUAL_FLOOR,
    GRADUAL_MIN_FRAMES,
    GRADUAL_SUM,
    HIST_BINS,
)
from filmanalyser.core.features import SHOT_CUTS

NAME = SHOT_CUTS
VERSION = 2  # v2: gradual transitions and merged cut spikes (DECISIONS #79)
FEATURES = ("cuts", "gradual", "max_diff")
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


def _runs(mask: npt.NDArray[np.bool_]) -> list[tuple[int, int]]:
    """Maximal [start, end) runs of True in `mask`."""
    padded = np.concatenate([[False], mask, [False]]).astype(np.int8)
    edges = np.flatnonzero(np.diff(padded))
    return [(int(a), int(b)) for a, b in zip(edges[::2], edges[1::2], strict=True)]


@dataclass(frozen=True)
class Segmentation:
    """What the distances say about a chunk: hard cuts (the frame where a new scene starts) and
    gradual transitions (dissolves, fades: the frames they span), as frame indices."""

    cuts: tuple[int, ...]
    gradual: tuple[tuple[int, int], ...]


def segment(distances: npt.NDArray[np.float64], context_frames: int) -> Segmentation:
    """Hard cuts and gradual transitions from consecutive frame distances (DECISIONS #79).

    Inside each run of distances above GRADUAL_FLOOR, spikes above CUT_DISTANCE split the run into
    stretches (the frames between spikes); adjacent spikes form one block. A stretch is gradual when
    it lasts GRADUAL_MIN_FRAMES and sums to GRADUAL_SUM. Two gradual stretches that meet at a block
    are one transition, and the block is part of it (a fade to black: the black frame is a block
    between two gradual stretches). Any other block is a cut. Cuts closer than CUT_MERGE_FRAMES are
    one cut. Only events owned by the core are returned."""
    first = max(1, context_frames)
    gradual: list[tuple[int, int]] = []
    cut_spikes: list[int] = []
    for run_start, run_end in _runs(distances > GRADUAL_FLOOR):
        spikes = [k for k in range(run_start, run_end) if distances[k] > CUT_DISTANCE]
        blocks = _spike_blocks(spikes)
        stretches = _stretches(run_start, run_end, blocks)
        ok = [_is_gradual(distances, a, b) for a, b in stretches]
        for index, (a, b) in enumerate(stretches):
            if not ok[index]:
                continue
            if index > 0 and ok[index - 1]:  # the block before joins this stretch to the last
                gradual[-1] = (gradual[-1][0], b + 1)
            else:
                gradual.append(
                    (a + 1, b + 1)
                )  # a transition starts at the frame after the stretch's first
        for index, (first_k, last_k) in enumerate(blocks):
            if not (
                ok[index] and ok[index + 1]
            ):  # a block between two gradual stretches is not a cut
                cut_spikes.append(max(range(first_k, last_k + 1), key=lambda k: distances[k]))
    cuts: list[int] = []
    for group in _merge_close(np.asarray(sorted(cut_spikes), dtype=np.intp)):
        best = max(group, key=lambda k: distances[k])
        if best + 1 >= first:
            cuts.append(int(best) + 1)
    owned = tuple(span for span in gradual if span[0] >= first)
    return Segmentation(tuple(cuts), owned)


def _is_gradual(distances: npt.NDArray[np.float64], a: int, b: int) -> bool:
    return b - a >= GRADUAL_MIN_FRAMES and float(distances[a:b].sum()) >= GRADUAL_SUM


def _stretches(
    run_start: int, run_end: int, blocks: list[tuple[int, int]]
) -> list[tuple[int, int]]:
    """The [start, end) frame-distance stretches of a run that lie between its spike blocks."""
    starts = [run_start] + [last + 1 for _, last in blocks]
    ends = [first for first, _ in blocks] + [run_end]
    return list(zip(starts, ends, strict=True))


def _spike_blocks(indices: list[int]) -> list[tuple[int, int]]:
    """Maximal runs of consecutive spike indices, as (first, last) pairs."""
    blocks: list[tuple[int, int]] = []
    for k in indices:
        if blocks and k == blocks[-1][1] + 1:
            blocks[-1] = (blocks[-1][0], k)
        else:
            blocks.append((k, k))
    return blocks


def _merge_close(spikes: npt.NDArray[np.intp]) -> list[list[int]]:
    """Group spike indices that lie within CUT_MERGE_FRAMES of their neighbour."""
    groups: list[list[int]] = []
    for index in (int(k) for k in spikes):
        if groups and index - groups[-1][-1] < CUT_MERGE_FRAMES:
            groups[-1].append(index)
        else:
            groups.append([index])
    return groups


def cut_positions(frames: Frames, context_frames: int) -> tuple[int, ...]:
    """Indices (into `frames`) of the frames where a hard cut starts, owned by the core."""
    return segment(frame_distances(frames), context_frames).cuts


@dataclass(frozen=True)
class ShotCuts:
    name: str = NAME
    version: int = VERSION
    features: tuple[str, ...] = FEATURES
    needs_audio: bool = False

    def extract(self, chunk: Chunk) -> Mapping[str, float]:
        distances = frame_distances(chunk.frames)
        seg = segment(distances, chunk.context_frames)
        core = distances[max(1, chunk.context_frames) - 1 :]  # distances that end on a core frame
        return {
            "cuts": float(len(seg.cuts)),
            "gradual": float(len(seg.gradual)),
            "max_diff": float(np.max(core)) if core.size else 0.0,
        }


EXTRACTOR = ShotCuts()
