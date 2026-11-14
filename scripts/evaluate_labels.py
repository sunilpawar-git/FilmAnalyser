"""Score the analysis against hand labels (format: docs/LABELS.md). Run locally on your own films:

    uv run --locked python scripts/evaluate_labels.py FILM FILM.labels [--cut-tolerance 0.25]

It reports precision and recall for speech, music and silence (per 32 ms window, over the windows
the labels cover), gradual transitions, hard cuts (within a tolerance), and the loudness gap against
the `ebur128` numbers in the label file. Films never leave the machine. The format and the scoring
are in label_format.py; this module runs the analysis.
"""

import argparse
import sys
from pathlib import Path

import numpy as np
import numpy.typing as npt

from filmanalyser.core.chunk import Chunk
from filmanalyser.core.config import (
    AUDIO_HIRES_RATE,
    AUDIO_RATE,
    LOUDNESS_BLOCK_S,
    LOUDNESS_HOP_S,
    VOICE_WINDOW,
    Config,
)
from filmanalyser.extractors._kweighting import k_weight
from filmanalyser.extractors._truepeak import true_peak_linear
from filmanalyser.extractors.loudness import block_energies, channel_weights, gated_lufs
from filmanalyser.extractors.shot_cuts import cut_positions, frame_distances, segment
from filmanalyser.extractors.speech_music import MUSIC, SILENCE, SPEECH, classify_windows
from filmanalyser.media.audio import PcmFormat, audio_stream, audio_window
from filmanalyser.media.paths import validate_input_path
from filmanalyser.media.probe import probe_video
from filmanalyser.pipeline.runner import chunk_stream
from label_format import (
    Labels,
    Score,
    Span,
    gap,
    inside,
    parse_labels,
    percent,
    score_cuts,
    score_gradual,
    score_kind,
)

__all__ = [
    "Labels",
    "Score",
    "Span",
    "gap",
    "inside",
    "parse_labels",
    "score_cuts",
    "score_gradual",
    "score_kind",
]

SEGMENT_S = 60.0  # film-level loudness is computed in segments this long (bounded memory)


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


def gradual_predictions(path: Path) -> list[tuple[float, float]]:
    """Gradual transitions the detector finds, as (start, end) film seconds."""
    found: list[tuple[float, float]] = []
    for chunk in chunk_stream(path, Config(), 0, None):
        if not isinstance(chunk, Chunk):
            raise TypeError("the decoder yields chunks")
        seg = segment(frame_distances(chunk.frames), chunk.context_frames)
        for a, b in seg.gradual:
            found.append((chunk.first_frame_s + a / chunk.fps, chunk.first_frame_s + b / chunk.fps))
    return found


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
    """Whole-film integrated loudness (LUFS) and true peak (dBFS), measured at 48 kHz as BS.1770
    specifies (DECISIONS #72). Blocks sit on one global grid and are gated together; the film is
    read in segments, so memory stays bounded."""
    stream = audio_stream(path)
    if stream is None:
        return None, None
    info = probe_video(path)
    rate = AUDIO_HIRES_RATE
    pcm = PcmFormat(stream.channels, rate)
    block = round(LOUDNESS_BLOCK_S * rate)
    hop = round(LOUDNESS_HOP_S * rate)
    weights = channel_weights(stream.channels)
    energies: list[npt.NDArray[np.float64]] = []
    peak = 0.0
    position = 0.0
    while position < info.duration_s:
        span = min(SEGMENT_S, info.duration_s - position)
        keep = -(-round(span * rate) // hop)  # block starts that fall inside this segment
        raw = audio_window(path, info.start_s + position, stream.start_s, span + block / rate, pcm)
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
                f"{name:8s} precision {percent(score.precision)}  recall {percent(score.recall)}"
                f"  ({score.count} windows labelled)"
            )
    else:
        lines.append("no audio track: speech, music and silence not scored")
    grad = score_gradual(labels, gradual_predictions(film))
    cuts = score_cuts(labels.cuts, cut_predictions(film), tolerance)
    lines.append(
        f"gradual  precision {percent(grad.precision)}  recall {percent(grad.recall)}"
        f"  ({grad.count} labelled transitions)"
    )
    lines.append(
        f"cuts     precision {percent(cuts.precision)}  recall {percent(cuts.recall)}"
        f"  ({cuts.count} labelled, tolerance {tolerance:.2f} s)"
    )
    lufs, true_peak = film_loudness(film)
    lines.append(_loudness_line("integrated", lufs, labels.ebur_integrated, "LUFS"))
    lines.append(_loudness_line("true peak", true_peak, labels.ebur_true_peak, "dBFS"))
    lines.append("note: loudness and true peak are measured at 48 kHz (BS.1770); speech at 16 kHz")
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
