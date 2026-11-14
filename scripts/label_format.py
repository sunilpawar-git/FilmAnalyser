"""The label format and the scoring (pure: no film is opened). docs/LABELS.md describes the format.

Spans (speech, music, silence, nospeech, gradual) and cuts are parsed and scored here. The
film-level runs and the report are in evaluate_labels.py, which re-exports these names."""

from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

SPAN_KINDS = (
    "speech",
    "music",
    "silence",
    "nospeech",
    "gradual",
)  # nospeech: labelled as no speech (AVA)


@dataclass(frozen=True)
class Span:
    kind: str
    start: float
    end: float


@dataclass(frozen=True)
class Labels:
    spans: tuple[Span, ...]
    cuts: tuple[float, ...]
    ebur_integrated: float | None = None
    ebur_true_peak: float | None = None


def parse_labels(text: str) -> Labels:
    """Parse a label file (docs/LABELS.md). Raises ValueError naming the line that is wrong."""
    spans: list[Span] = []
    cuts: list[float] = []
    ebur: dict[str, float] = {}
    for number, raw in enumerate(text.splitlines(), start=1):
        tokens = raw.split("#", 1)[0].split()
        if not tokens:
            continue
        try:
            if tokens[0] in SPAN_KINDS and len(tokens) == 3:
                start, end = float(tokens[1]), float(tokens[2])
                if not 0 <= start < end:
                    raise ValueError("a span needs 0 <= start < end")
                spans.append(Span(tokens[0], start, end))
            elif tokens[0] == "cut" and len(tokens) == 2:
                cuts.append(float(tokens[1]))
            elif tokens[0] in ("ebur128_integrated", "ebur128_true_peak") and len(tokens) == 2:
                ebur[tokens[0]] = float(tokens[1])
            else:
                raise ValueError("unknown line")
        except ValueError as error:
            raise ValueError(f"line {number}: {error}: {raw.strip()!r}") from None
    _check_no_overlap(spans)
    return Labels(
        tuple(spans),
        tuple(sorted(cuts)),
        ebur.get("ebur128_integrated"),
        ebur.get("ebur128_true_peak"),
    )


def _check_no_overlap(spans: list[Span]) -> None:
    for kind in SPAN_KINDS:
        same = sorted((s for s in spans if s.kind == kind), key=lambda s: s.start)
        for before, after in zip(same, same[1:], strict=False):
            if after.start < before.end:
                raise ValueError(f"{kind} spans overlap at {after.start} s")


def inside(
    spans: tuple[Span, ...], kind: str, times: npt.NDArray[np.float64]
) -> npt.NDArray[np.bool_]:
    """For each time: is it inside a span of `kind`?"""
    mask = np.zeros(len(times), dtype=bool)
    for span in spans:
        if span.kind == kind:
            mask |= (times >= span.start) & (times < span.end)
    return mask


@dataclass(frozen=True)
class Score:
    precision: float | None
    recall: float | None
    count: int


def score_kind(
    labels: Labels,
    kind: str,
    times: npt.NDArray[np.float64],
    predicted: npt.NDArray[np.bool_],
) -> Score:
    """Precision and recall for one kind over the windows the labels cover (any span counts as
    covered, so a window labelled only as music is a negative for speech)."""
    covered = np.zeros(len(times), dtype=bool)
    for span in labels.spans:
        covered |= (times >= span.start) & (times < span.end)
    positive = inside(labels.spans, kind, times)
    use = covered
    truth, guess = positive[use], predicted[use]
    true_pos = int(np.count_nonzero(truth & guess))
    guessed = int(np.count_nonzero(guess))
    actual = int(np.count_nonzero(truth))
    return Score(
        true_pos / guessed if guessed else None,
        true_pos / actual if actual else None,
        int(use.sum()),
    )


def score_cuts(truth: tuple[float, ...], found: npt.NDArray[np.float64], tolerance: float) -> Score:
    """Each found cut counts as right if a labelled cut is within `tolerance` seconds, and each
    labelled cut counts as found if a detected cut is within it."""
    if found.size == 0:
        precision = None
    else:
        hits = sum(1 for f in found if any(abs(f - t) <= tolerance for t in truth))
        precision = hits / found.size
    if not truth:
        recall = None
    else:
        matched = sum(1 for t in truth if np.any(np.abs(found - t) <= tolerance))
        recall = matched / len(truth)
    return Score(precision, recall, len(truth))


def gap(ours: float | None, reference: float | None) -> float | None:
    return None if ours is None or reference is None else ours - reference


def percent(value: float | None) -> str:
    return "n/a" if value is None else f"{100 * value:.1f}%"


def score_gradual(labels: Labels, detected: list[tuple[float, float]]) -> Score:
    """Gradual transitions: a detection is right when it overlaps a labelled transition, and a
    labelled transition is found when a detection overlaps it."""
    truth = [(s.start, s.end) for s in labels.spans if s.kind == "gradual"]
    if not detected:
        precision = None
    else:
        hits = sum(1 for a, b in detected if any(a < e and b > c for c, e in truth))
        precision = hits / len(detected)
    if not truth:
        recall = None
    else:
        found = sum(1 for c, e in truth if any(a < e and b > c for a, b in detected))
        recall = found / len(truth)
    return Score(precision, recall, len(truth))
