"""Improvement 5: the same input gives byte-identical feature files, run after run."""

import time
from pathlib import Path

import pytest

from tests.fixtures.make_synthetic import make_clip
from tests.integration._pipeline import run_film, tree


@pytest.fixture(scope="module")
def film(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return make_clip(tmp_path_factory.mktemp("film") / "film.mp4", seconds=60)


def test_two_runs_over_the_same_film_are_byte_identical(film: Path, tmp_path: Path) -> None:
    run_film(film, tmp_path / "first")
    time.sleep(1.1)  # a timestamp anywhere in the output (Parquet or manifest) would now differ
    run_film(film, tmp_path / "second")
    first, second = tree(tmp_path / "first"), tree(tmp_path / "second")
    assert first.keys() == second.keys()
    assert len(first) == 7  # manifest + 6 chunk files: the comparison is not vacuous
    for name in first:
        assert first[name] == second[name], name


def test_the_directory_name_and_location_do_not_leak_into_the_files(
    film: Path, tmp_path: Path
) -> None:
    run_film(film, tmp_path / "one")
    run_film(film, tmp_path / "somewhere" / "else" / "two")
    assert tree(tmp_path / "one") == tree(tmp_path / "somewhere" / "else" / "two")
    assert b"somewhere" not in b"".join(tree(tmp_path / "somewhere" / "else" / "two").values())


def test_a_second_run_over_a_finished_store_changes_nothing_and_decodes_nothing(
    film: Path, tmp_path: Path
) -> None:
    """Stages are idempotent (DECISIONS #19): same input + same feature version = cache hit."""
    run_film(film, tmp_path / "s")
    before = tree(tmp_path / "s")
    decoded: list[int] = []
    store = run_film(film, tmp_path / "s", on_decoded=decoded.append)
    assert decoded == [] and store.complete
    assert tree(tmp_path / "s") == before
