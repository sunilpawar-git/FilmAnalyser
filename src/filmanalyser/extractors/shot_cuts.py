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
    CUT_BAND_FLOOR,
    CUT_CALM_P90,
    CUT_CALM_RADIUS,
    CUT_DISTANCE,
    CUT_MERGE_FRAMES,
    GRADUAL_BLEND_RESIDUAL,
    GRADUAL_FLOOR,
    GRADUAL_MIN_FRAMES,
    GRADUAL_SUM,
    HIST_BINS,
)
from filmanalyser.core.features import SHOT_CUTS

NAME = SHOT_CUTS
VERSION = 4  # v4: blend test (#84); v3: calm-second cuts (#83); v2: gradual, merged cuts (#79)
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


def segment(
    distances: npt.NDArray[np.float64], context_frames: int, frames: Frames | None = None
) -> Segmentation:
    """Hard cuts and gradual transitions from consecutive frame distances (DECISIONS #79).

    Inside each run of distances above GRADUAL_FLOOR, spikes above CUT_DISTANCE split the run into
    stretches (the frames between spikes); adjacent spikes form one block. A stretch is gradual when
    it lasts GRADUAL_MIN_FRAMES and sums to GRADUAL_SUM. Two gradual stretches that meet at a block
    are one transition, and the block is part of it (a fade to black: the black frame is a block
    between two gradual stretches). Any other block is a cut. Cuts closer than CUT_MERGE_FRAMES are
    one cut. Only events owned by the core are returned. With `frames`, a gradual stretch must also
    be a blend of its first and last frames (`blend_residual`), which rejects flashes, effects and
    camera moves (DECISIONS #84)."""
    first = max(1, context_frames)
    gradual: list[tuple[int, int]] = []
    cut_spikes: list[int] = []
    for run_start, run_end in _runs(distances > GRADUAL_FLOOR):
        spans, spikes = _scan_run(distances, run_start, run_end, frames)
        gradual += spans
        cut_spikes += spikes
    cuts: list[int] = []
    for group in _merge_close(np.asarray(sorted(cut_spikes), dtype=np.intp)):
        best = max(group, key=lambda k: distances[k])
        if best + 1 >= first:
            cuts.append(int(best) + 1)
    owned = tuple(span for span in gradual if span[0] >= first)
    return Segmentation(tuple(cuts), owned)


def _scan_run(
    distances: npt.NDArray[np.float64], run_start: int, run_end: int, frames: Frames | None
) -> tuple[list[tuple[int, int]], list[int]]:
    """One run's gradual transitions (as frame spans) and the spike indices that are cuts."""
    blocks = _spike_blocks([k for k in range(run_start, run_end) if _is_spike(distances, k)])
    stretches = _stretches(run_start, run_end, blocks)
    ok = [_is_gradual(distances, a, b, frames) for a, b in stretches]
    spans: list[tuple[int, int]] = []
    for index, (a, b) in enumerate(stretches):
        if not ok[index]:
            continue
        if index > 0 and ok[index - 1]:  # the block before joins this stretch to the last
            spans[-1] = (spans[-1][0], b + 1)
        else:
            spans.append(
                (a + 1, b + 1)
            )  # a transition starts at the frame after the stretch's first
    cuts = [
        max(range(first_k, last_k + 1), key=lambda k: distances[k])
        for index, (first_k, last_k) in enumerate(blocks)
        if not (ok[index] and ok[index + 1])  # a block between two gradual stretches is not a cut
    ]
    return spans, cuts


def _is_spike(distances: npt.NDArray[np.float64], k: int) -> bool:
    """A cut-like change (DECISIONS #83): above CUT_DISTANCE, or above CUT_BAND_FLOOR in a calm
    second. Effects, explosions and fast motion make the second around a change busy; a cut between
    two steady shots stands alone."""
    value = float(distances[k])
    if value > CUT_DISTANCE:
        return True
    if value <= CUT_BAND_FLOOR:
        return False
    lo, hi = max(0, k - CUT_CALM_RADIUS), min(len(distances), k + CUT_CALM_RADIUS + 1)
    around = np.concatenate([distances[lo:k], distances[k + 1 : hi]])
    return around.size > 0 and float(np.percentile(around, 90)) < CUT_CALM_P90


def _is_gradual(distances: npt.NDArray[np.float64], a: int, b: int, frames: Frames | None) -> bool:
    if b - a < GRADUAL_MIN_FRAMES or float(distances[a:b].sum()) < GRADUAL_SUM:
        return False
    return frames is None or blend_residual(frames, a, b) <= GRADUAL_BLEND_RESIDUAL


def blend_residual(frames: Frames, first: int, last: int) -> float:
    """How far the frames strictly between `first` and `last` are from the best blend of those two
    frames, relative to how different the two are: 0 for a perfect dissolve or fade, about 1 or more
    for motion, flashes and effects. Grey levels, so colour grading does not count."""
    start = frames[first].astype(np.float64).mean(axis=2)
    change = frames[last].astype(np.float64).mean(axis=2) - start
    span = float(np.linalg.norm(change)) + 1e-9
    gaps = []
    for index in range(first + 1, last):
        offset = frames[index].astype(np.float64).mean(axis=2) - start
        alpha = float(np.clip(np.sum(offset * change) / span**2, 0.0, 1.0))
        gaps.append(float(np.linalg.norm(offset - alpha * change)) / span)
    return float(np.mean(gaps)) if gaps else 0.0


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
    return segment(frame_distances(frames), context_frames, frames).cuts


@dataclass(frozen=True)
class ShotCuts:
    name: str = NAME
    version: int = VERSION
    features: tuple[str, ...] = FEATURES
    needs_audio: bool = False

    def extract(self, chunk: Chunk) -> Mapping[str, float]:
        distances = frame_distances(chunk.frames)
        seg = segment(distances, chunk.context_frames, chunk.frames)
        core = distances[max(1, chunk.context_frames) - 1 :]  # distances that end on a core frame
        return {
            "cuts": float(len(seg.cuts)),
            "gradual": float(len(seg.gradual)),
            "max_diff": float(np.max(core)) if core.size else 0.0,
        }


EXTRACTOR = ShotCuts()
