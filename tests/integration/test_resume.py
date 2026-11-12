"""Kill-and-resume on a real subprocess: SIGKILL a worker mid-film, resume, and prove that the
finished chunks were not decoded again and that the result equals an uninterrupted run."""

from pathlib import Path

import pytest

from filmanalyser.core.errors import StorageError
from filmanalyser.pipeline.runner import analyse
from tests.fixtures.make_synthetic import make_clip
from tests.fixtures.store import CONFIG, tree
from tests.integration._kill import decoded, run_to_end, run_until_killed

TOTAL = 12  # a 120 s film in 10 s chunks


@pytest.fixture(scope="module")
def film(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return make_clip(tmp_path_factory.mktemp("film") / "film.mp4", seconds=120)


@pytest.fixture(scope="module")
def reference(film: Path, tmp_path_factory: pytest.TempPathFactory) -> dict[str, bytes]:
    """The uninterrupted run everything else must equal."""
    directory = tmp_path_factory.mktemp("reference")
    analyse(film, directory, CONFIG)
    return tree(directory)


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
    store = analyse(film, tmp_path / "out", CONFIG)  # resumes and finishes
    assert store.complete and store.next_chunk == TOTAL


def test_resuming_with_a_different_film_is_rejected(film: Path, tmp_path: Path) -> None:
    run_until_killed(film, tmp_path / "out", 2)
    other = make_clip(tmp_path / "other.mp4", seconds=120, size=(320, 180), fps=12)
    with pytest.raises(StorageError) as caught:
        analyse(other, tmp_path / "out", CONFIG)
    assert caught.value.key == "error.storage.input_mismatch"
