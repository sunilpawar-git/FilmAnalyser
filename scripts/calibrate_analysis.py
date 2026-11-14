"""Reproduce the numbers behind ACT_MIN_SCORE and TENSION_MIN_PEAK_Z (DECISIONS #92).

From the repository root: `PYTHONPATH=. python scripts/calibrate_analysis.py`. It runs the analyses
on structure-free noise films (many seeds, several lengths, with and without audio columns) and on
single-step films, and prints the largest change score and tension peak that noise produces beside
the score a real step gets. Synthetic data only: it says nothing about real films.
"""

import numpy as np
from tests.fixtures.timelines import block_film, noise_film

from filmanalyser.analysis.act_breaks import ActSettings, change_scores, find_act_breaks
from filmanalyser.analysis.tension import analyse_tension
from filmanalyser.analysis.timeline import build_timeline, film_state
from filmanalyser.core.config import ACT_SMOOTH_CHUNKS, ACT_WINDOW_CHUNKS

SEEDS = range(300)
LENGTHS = (60, 120, 180, 400)


def noise_maxima(count: int, *, audio: bool) -> tuple[float, float]:
    """The largest change score and tension peak over all seeds of one kind of noise film."""
    scores, peaks = [], []
    for seed in SEEDS:
        timeline = build_timeline(noise_film(count, seed, audio=audio))
        _, state = film_state(timeline, ACT_SMOOTH_CHUNKS)
        scores.append(np.nanmax(change_scores(state, ACT_WINDOW_CHUNKS)))
        peaks.append(max(analyse_tension(timeline).values))
    return float(max(scores)), float(max(peaks))


def step_score(position: float, levels: tuple[float, float]) -> float:
    first = round(100 * position)
    film = block_film([first, 100 - first], list(levels))
    breaks = find_act_breaks(build_timeline(film), ActSettings(min_score=0.0)).breaks
    return breaks[0].score if breaks else 0.0


def main() -> int:
    print(f"noise films: {len(SEEDS)} seeds per row; maxima over all seeds")
    for count in LENGTHS:
        for audio in (True, False):
            score, peak = noise_maxima(count, audio=audio)
            print(f"  {count:3d} chunks, audio={audio!s:5}: score {score:.2f}, tension {peak:.2f}")
    print("a step in every feature, as a share of the film:")
    for position in (0.2, 0.3):
        print(f"  at {position:.0%}: change score {step_score(position, (1.0, 3.0)):.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
