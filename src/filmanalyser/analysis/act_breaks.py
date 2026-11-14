"""Act breaks: where the film's state changes most, kept only inside the two classical zones.

The state of each chunk is a vector of z-scored features (cut rate, loudness, speech, tonal and
silence shares, picture features), smoothed over a few chunks. A boundary is scored by how far the
mean state of the W chunks after it lies from the mean of the W chunks before it. Strong local
maxima are candidates; at most one candidate per zone becomes a break. Nothing is ever forced: a
zone without a candidate above the threshold has no break and the result says so (DECISIONS #90).
Pure and deterministic: the same timeline always gives the same result.
"""

from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

from filmanalyser.analysis.timeline import Timeline, film_state
from filmanalyser.core.config import (
    ACT_MAX_BREAKS,
    ACT_MIN_GAP_CHUNKS,
    ACT_MIN_SCORE,
    ACT_SMOOTH_CHUNKS,
    ACT_TIE_FRACTION,
    ACT_TOP_FEATURES,
    ACT_WINDOW_CHUNKS,
    ACT_ZONE_1,
    ACT_ZONE_2,
    ACT_ZONE_PRIORS,
)

Matrix = npt.NDArray[np.float64]
ZONES = (ACT_ZONE_1, ACT_ZONE_2)


@dataclass(frozen=True)
class ActSettings:
    """The tunable numbers; the defaults are the config's, tests vary them one at a time."""

    smooth_chunks: int = ACT_SMOOTH_CHUNKS
    window: int = ACT_WINDOW_CHUNKS
    min_score: float = ACT_MIN_SCORE
    min_gap: int = ACT_MIN_GAP_CHUNKS
    tie_fraction: float = ACT_TIE_FRACTION


@dataclass(frozen=True)
class ActBreak:
    boundary: int  # the break lies between chunk boundary-1 and chunk `boundary`
    time_s: float  # container clock: the start of chunk `boundary`
    score: float  # distance between the windows, in standard deviations per feature
    moved: tuple[str, ...]  # the features that moved most across it, largest first


@dataclass(frozen=True)
class Act:
    start_s: float
    end_s: float


@dataclass(frozen=True)
class ActBreaks:
    breaks: tuple[ActBreak, ...]
    acts: tuple[Act, ...]
    empty_zones: tuple[int, ...]  # zone numbers (1, 2) in which no break was found
    features_used: tuple[str, ...]
    audio_used: bool  # False: the breaks come from the picture alone
    scored: int  # how many boundaries could be scored (none for a film under two windows)


def _window_mean(matrix: Matrix, first: int, last: int) -> Matrix:
    """Per-feature mean of rows first..last-1 over the measured values (NaN when none)."""
    block = matrix[first:last]
    measured = np.isfinite(block)
    total = np.where(measured, block, 0.0).sum(axis=0)
    count = measured.sum(axis=0)
    return np.where(count > 0, total / np.maximum(count, 1), np.nan)


def _difference(matrix: Matrix, boundary: int, window: int) -> Matrix:
    after = _window_mean(matrix, boundary, boundary + window)
    return after - _window_mean(matrix, boundary - window, boundary)


def change_scores(matrix: Matrix, window: int) -> Matrix:
    """Score of every boundary: Euclidean distance between the window means before and after it,
    over the features measured on both sides, divided by the square root of their number. NaN where
    a boundary lies closer than `window` chunks to either end of the film."""
    count = len(matrix)
    scores = np.full(count + 1, np.nan)
    for boundary in range(window, count - window + 1):
        diff = _difference(matrix, boundary, window)
        used = np.isfinite(diff)
        if used.any():
            scores[boundary] = float(np.sqrt(np.sum(diff[used] ** 2) / used.sum()))
    return scores


def _local_maxima(scores: Matrix, floor: float, window: int) -> list[int]:
    found = []
    for t in np.flatnonzero(np.isfinite(scores) & (scores > floor)):
        around = scores[max(0, t - window) : t + window + 1]
        earlier = scores[max(0, t - window) : t]
        if scores[t] >= np.nanmax(around) and not np.any(earlier >= scores[t]):
            found.append(int(t))  # of equal neighbours, the first
    return found


def _merged(candidates: list[int], scores: Matrix, gap: int) -> list[int]:
    kept: list[int] = []
    for t in sorted(candidates, key=lambda c: (-scores[c], c)):
        if all(abs(t - other) >= gap for other in kept):
            kept.append(t)
    return sorted(kept)


def _pick(
    candidates: list[int], scores: Matrix, fractions: Matrix, tie_fraction: float, prior: float
) -> int:
    """The strongest candidate; among those within the tie fraction of it, the one nearest the
    classical position `prior` (a tie-break only: it never creates or promotes a break)."""
    best = max(scores[t] for t in candidates)
    tied = [t for t in candidates if scores[t] >= best * (1.0 - tie_fraction)]
    return min(tied, key=lambda t: (abs(fractions[t] - prior), t))


def _choose(
    candidates: list[int], scores: Matrix, fractions: Matrix, tie: float
) -> tuple[list[int], list[int]]:
    chosen: list[int] = []
    empty: list[int] = []
    for number, ((low, high), prior) in enumerate(zip(ZONES, ACT_ZONE_PRIORS, strict=True), 1):
        inside = [t for t in candidates if low <= fractions[t] <= high]
        if inside and len(chosen) < ACT_MAX_BREAKS:
            chosen.append(_pick(inside, scores, fractions, tie, prior))
        else:
            empty.append(number)
    return chosen, empty


def _moved(matrix: Matrix, boundary: int, window: int, names: tuple[str, ...]) -> tuple[str, ...]:
    diff = _difference(matrix, boundary, window)
    size = np.where(np.isfinite(diff), np.abs(diff), -np.inf)  # a feature never measured loses
    order = sorted(range(len(names)), key=lambda i: (-size[i], i))
    return tuple(names[i] for i in order[:ACT_TOP_FEATURES] if np.isfinite(size[i]))


def _acts(timeline: Timeline, times: list[float]) -> tuple[Act, ...]:
    if timeline.count == 0:
        return ()
    edges = [0.0, *times, timeline.film_end_s]
    return tuple(Act(a, b) for a, b in zip(edges, edges[1:], strict=False))


def find_act_breaks(timeline: Timeline, settings: ActSettings | None = None) -> ActBreaks:
    settings = settings or ActSettings()
    names, matrix = film_state(timeline, settings.smooth_chunks)
    scores = change_scores(matrix, settings.window)
    scored = int(np.isfinite(scores).sum())
    found = _merged(
        _local_maxima(scores, settings.min_score, settings.window), scores, settings.min_gap
    )
    fractions = np.append(timeline.start_s, timeline.film_end_s) / max(timeline.film_end_s, 1.0)
    chosen, empty = _choose(found, scores, fractions, settings.tie_fraction)
    breaks = tuple(
        ActBreak(
            t,
            float(timeline.start_s[t]),
            float(scores[t]),
            _moved(matrix, t, settings.window, names),
        )
        for t in sorted(chosen)
    )
    return ActBreaks(
        breaks=breaks,
        acts=_acts(timeline, [b.time_s for b in breaks]),
        empty_zones=tuple(empty),
        features_used=names,
        audio_used=timeline.audio_used,
        scored=scored,
    )
