"""Child process for the kill-and-resume tests: analyse a film into a store, printing progress.
With a gate N it waits (still mid-film, decoder and ffmpeg alive) after storing N chunks, until the
parent kills it with SIGKILL. The profile picks the settings: the synthetic clip or real footage."""

import sys
from pathlib import Path

from filmanalyser.core.config import Config
from filmanalyser.pipeline.runner import analyse
from tests.fixtures.store import CONFIG as SYNTHETIC

# Real footage: chunks of 10.25 s at 12 fps, so the resume points fall between source frames of
# typical footage (DECISIONS #54).
REAL = Config(chunk_seconds=10.25, overlap_seconds=1.0, analysis_fps=12.0, frame_width=160)
PROFILES = {"synthetic": SYNTHETIC, "real": REAL}


def say(text: str) -> None:
    print(text, flush=True)


def main(film: str, directory: str, gate: int, profile: str) -> None:
    stored = 0

    def on_stored(index: int) -> None:
        nonlocal stored
        stored += 1
        say(f"stored {index}")
        if gate and stored == gate:
            say(f"gate {gate}")
            sys.stdin.read()  # blocks until the parent kills this process

    store = analyse(
        Path(film),
        Path(directory),
        PROFILES[profile],
        on_decoded=lambda i: say(f"decoded {i}"),
        on_stored=on_stored,
    )
    say(f"done {store.next_chunk}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], int(sys.argv[3]), sys.argv[4])
