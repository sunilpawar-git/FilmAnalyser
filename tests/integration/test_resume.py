"""Kill-and-resume on a real subprocess: SIGKILL a worker mid-film, resume, and prove that the
finished chunks were not decoded again and that the result equals an uninterrupted run."""

import signal
import subprocess
import sys
import threading
from pathlib import Path

import pytest

from filmanalyser.core.errors import StorageError
from tests.fixtures.make_synthetic import make_clip
from tests.integration._pipeline import run_film, tree

REPO = Path(__file__).resolve().parents[2]
TOTAL = 12  # a 120 s film in 10 s chunks
WATCHDOG_S = 120


@pytest.fixture(scope="module")
def film(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return make_clip(tmp_path_factory.mktemp("film") / "film.mp4", seconds=120)


@pytest.fixture(scope="module")
def reference(film: Path, tmp_path_factory: pytest.TempPathFactory) -> dict[str, bytes]:
    """The uninterrupted run everything else must equal."""
    directory = tmp_path_factory.mktemp("reference")
    run_film(film, directory)
    return tree(directory)


def start(film: Path, directory: Path, gate: int) -> subprocess.Popen[str]:
    argv = [sys.executable, "-m", "tests.integration._resume_worker", str(film), str(directory)]
    proc = subprocess.Popen(
        [*argv, str(gate)],
        cwd=REPO,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    watchdog = threading.Timer(WATCHDOG_S, proc.kill)  # a hung worker must fail, not hang
    watchdog.daemon = True  # and a finished test must not wait for it
    watchdog.start()
    return proc


def run_until_killed(film: Path, directory: Path, gate: int) -> list[str]:
    """Run a worker until it has stored `gate` chunks, then SIGKILL it; return its output."""
    proc = start(film, directory, gate)
    assert proc.stdout is not None
    lines: list[str] = []
    for line in proc.stdout:
        lines.append(line.strip())
        if line.strip() == f"gate {gate}":
            break
    else:
        pytest.fail(f"worker ended before the gate: {lines} {proc.communicate()[1]}")
    proc.send_signal(signal.SIGKILL)
    assert proc.wait() == -signal.SIGKILL  # killed for real, not exited
    return lines


def run_to_end(film: Path, directory: Path) -> list[str]:
    proc = start(film, directory, 0)
    out, err = proc.communicate(input="")
    assert proc.returncode == 0, err
    return out.split()


def decoded(lines: list[str]) -> list[int]:
    words = " ".join(lines).split()
    return [int(words[i + 1]) for i, w in enumerate(words) if w == "decoded"]


@pytest.mark.parametrize("gate", [1, 5, 11])
def test_kill_mid_film_then_resume_equals_an_uninterrupted_run(
    film: Path, tmp_path: Path, reference: dict[str, bytes], gate: int
) -> None:
    store = tmp_path / "out"
    first = run_until_killed(film, store, gate)
    assert decoded(first) == list(range(gate))  # it was killed part-way through the film

    resumed = run_to_end(film, store)
    assert decoded(resumed) == list(range(gate, TOTAL))  # finished chunks are NOT decoded again
    assert resumed[-2:] == ["done", str(TOTAL)]
    assert tree(store) == reference  # same bytes as if nothing had happened


def test_killed_twice_still_converges(
    film: Path, tmp_path: Path, reference: dict[str, bytes]
) -> None:
    store = tmp_path / "out"
    run_until_killed(film, store, 3)
    second = run_until_killed(film, store, 4)  # 4 more chunks in this run: chunks 3..6
    assert decoded(second) == [3, 4, 5, 6]
    last = run_to_end(film, store)
    assert decoded(last) == list(range(7, TOTAL))
    assert tree(store) == reference


def test_a_kill_leaves_a_store_that_opens_cleanly(film: Path, tmp_path: Path) -> None:
    run_until_killed(film, tmp_path / "out", 5)
    store = run_film(film, tmp_path / "out", on_stored=lambda _: None)  # resumes and finishes
    assert store.complete and store.next_chunk == TOTAL


def test_resuming_with_a_different_film_is_rejected(film: Path, tmp_path: Path) -> None:
    run_until_killed(film, tmp_path / "out", 2)
    other = make_clip(tmp_path / "other.mp4", seconds=120, size=(320, 180), fps=12)
    with pytest.raises(StorageError) as caught:
        run_film(other, tmp_path / "out")
    assert caught.value.key == "error.storage.input_mismatch"
