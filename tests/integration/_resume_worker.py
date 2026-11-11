"""Child process for the kill-and-resume test: analyse a film into a store, reporting progress on
stdout. With a gate N it stops after storing N chunks and waits (still mid-film: the decoder and
ffmpeg are alive) until the parent kills it with SIGKILL."""

import sys
from pathlib import Path

from tests.integration._pipeline import run_film


def say(text: str) -> None:
    print(text, flush=True)


def main(film: str, directory: str, gate: int) -> None:
    stored = 0

    def on_stored(index: int) -> None:
        nonlocal stored
        stored += 1
        say(f"stored {index}")
        if gate and stored == gate:
            say(f"gate {gate}")
            sys.stdin.read()  # blocks until killed (stdin is an open pipe the parent never closes)

    store = run_film(Path(film), Path(directory), lambda i: say(f"decoded {i}"), on_stored)
    say(f"done {store.next_chunk}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], int(sys.argv[3]))
