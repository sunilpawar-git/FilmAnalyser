"""Score the analysis against hand labels (format: docs/LABELS.md). Run locally on your own films:

    uv run --locked python scripts/evaluate_labels.py FILM FILM.labels [--cut-tolerance 0.25]

It reports precision and recall for speech, music and silence (per 32 ms window, over the windows
the labels cover), precision and recall for hard cuts (within a tolerance), and the loudness gap
against the `ebur128` numbers in the label file. Films never leave the machine.

The parsing and the scoring are pure functions (tested in tests/unit/test_evaluate_labels.py); the
film-level run uses the same decoder, voice model, classifier and gating as the pipeline.
"""

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import numpy.typing as npt

from filmanalyser.core.chunk import Chunk
from filmanalyser.core.config import (
    AUDIO_RATE,
    LOUDNESS_BLOCK_S,
    LOUDNESS_HOP_S,
    VOICE_WINDOW,
    Config,
)
from filmanalyser.extractors._kweighting import k_weight
from filmanalyser.extractors._truepeak import true_peak_linear
from filmanalyser.extractors.loudness import block_energies, channel_weights, gated_lufs
from filmanalyser.extractors.shot_cuts import cut_positions
from filmanalyser.extractors.speech_music import MUSIC, SILENCE, SPEECH, classify_windows
from filmanalyser.media.audio import audio_stream, audio_window
from filmanalyser.media.paths import validate_input_path
from filmanalyser.media.probe import probe_video
from filmanalyser.pipeline.runner import chunk_stream

SPAN_KINDS = ("speech", "music", "silence")
SEGMENT_S = 60.0  # film-level loudness is computed in segments this long (bounded memory)


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


def _percent(value: float | None) -> str:
    return "n/a" if value is None else f"{100 * value:.1f}%"


def window_predictions(path: Path) -> tuple[npt.NDArray[np.float64], npt.NDArray[np.int64]]:
    """Window start times (film seconds) and the classifier's label for every core window."""
    times: list[float] = []
    labels: list[int] = []
    for chunk in chunk_stream(path, Config(), 0, audio_stream(path)):
        if chunk.audio is None or chunk.audio.voice is None:
            continue
        mono = np.mean(chunk.audio.samples, axis=1, dtype=np.float64)
        offset = chunk.audio_core_offset
        window_labels = classify_windows(mono, chunk.audio.voice, offset)
        for index, label in enumerate(window_labels):
            start = index * VOICE_WINDOW
            if start >= offset:
                times.append(chunk.first_frame_s + (start + VOICE_WINDOW / 2) / AUDIO_RATE)
                labels.append(int(label))
    return np.asarray(times), np.asarray(labels, dtype=np.int64)


def cut_predictions(path: Path) -> npt.NDArray[np.float64]:
    """Hard-cut times the shot detector finds (the same ownership rule as the pipeline)."""
    found: list[float] = []
    for chunk in chunk_stream(path, Config(), 0, None):
        if not isinstance(chunk, Chunk):
            raise TypeError("the decoder yields chunks")
        for position in cut_positions(chunk.frames, chunk.context_frames):
            found.append(chunk.first_frame_s + position / chunk.fps)
    return np.asarray(found, dtype=np.float64)


def film_loudness(path: Path) -> tuple[float | None, float | None]:
    """Whole-film integrated loudness (LUFS) and true peak (dBFS) at the analysis rate.

    Blocks sit on one global grid and are gated together, as BS.1770 requires; the film is read
    in segments, so memory stays bounded."""
    stream = audio_stream(path)
    if stream is None:
        return None, None
    info = probe_video(path)
    rate = AUDIO_RATE
    block = round(LOUDNESS_BLOCK_S * rate)
    hop = round(LOUDNESS_HOP_S * rate)
    weights = channel_weights(stream.channels)
    energies: list[npt.NDArray[np.float64]] = []
    peak = 0.0
    position = 0.0
    while position < info.duration_s:
        span = min(SEGMENT_S, info.duration_s - position)
        keep = -(-round(span * rate) // hop)  # block starts that fall inside this segment
        raw = audio_window(
            path, info.start_s + position, stream.start_s, span + block / rate, stream.channels
        )
        weighted = k_weight(raw, rate)
        energies.append(block_energies(weighted, block, hop, weights)[:keep])
        peak = max(peak, true_peak_linear(raw[: round(span * rate)].astype(np.float64), 0))
        position += SEGMENT_S
    lufs = gated_lufs(np.concatenate(energies)) if energies else None
    true_peak = 20 * float(np.log10(peak)) if peak > 0 else None
    return lufs, true_peak


def report(labels: Labels, film: Path, tolerance: float) -> list[str]:
    lines = [f"film: {film.name}"]
    times, predicted = window_predictions(film)
    if times.size:
        speech = score_kind(labels, "speech", times, predicted == SPEECH)
        music = score_kind(labels, "music", times, predicted == MUSIC)
        silence = score_kind(labels, "silence", times, predicted == SILENCE)
        for name, score in (("speech", speech), ("music", music), ("silence", silence)):
            lines.append(
                f"{name:8s} precision {_percent(score.precision)}  recall {_percent(score.recall)}"
                f"  ({score.count} windows labelled)"
            )
    else:
        lines.append("no audio track: speech, music and silence not scored")
    cuts = score_cuts(labels.cuts, cut_predictions(film), tolerance)
    lines.append(
        f"cuts     precision {_percent(cuts.precision)}  recall {_percent(cuts.recall)}"
        f"  ({cuts.count} labelled, tolerance {tolerance:.2f} s)"
    )
    lufs, true_peak = film_loudness(film)
    lines.append(_loudness_line("integrated", lufs, labels.ebur_integrated, "LUFS"))
    lines.append(_loudness_line("true peak", true_peak, labels.ebur_true_peak, "dBFS"))
    lines.append(
        "note: audio is analysed at 16 kHz; true peak reads low where content is above 8 kHz "
        "(about 0.4 dB on the first clip; see DECISIONS #68)"
    )
    return lines


def _loudness_line(name: str, ours: float | None, reference: float | None, unit: str) -> str:
    if ours is None:
        return f"{name:9s} no audio"
    if reference is None:
        return f"{name:9s} ours {ours:.2f} {unit} (no ebur128 reading in the label file)"
    return (
        f"{name:9s} ours {ours:.2f} {unit}, ebur128 {reference:.2f} {unit}, "
        f"gap {gap(ours, reference):+.2f} LU"
    )


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Score the analysis against hand labels.")
    parser.add_argument("film", type=Path)
    parser.add_argument("labels", type=Path)
    parser.add_argument("--cut-tolerance", type=float, default=0.25)
    args = parser.parse_args(argv)
    film = validate_input_path(args.film)
    try:
        labels = parse_labels(args.labels.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        print(f"labels not read: {error}", file=sys.stderr)
        return 2
    for line in report(labels, film, args.cut_tolerance):
        print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
