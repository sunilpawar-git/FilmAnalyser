import pytest

from filmanalyser.core.errors import (
    ERROR_TAXONOMY,
    AnalysisError,
    DecodeError,
    FilmAnalyserError,
    InputError,
    ModelError,
    ResourceError,
    StorageError,
)


def test_taxonomy_covers_every_category() -> None:
    assert {InputError, DecodeError, ModelError, StorageError, AnalysisError} <= set(ERROR_TAXONOMY)


def test_every_taxonomy_member_derives_from_base() -> None:
    assert all(issubclass(cls, FilmAnalyserError) for cls in ERROR_TAXONOMY)


def test_exit_codes_are_stable() -> None:
    codes = {cls.__name__: cls.exit_code for cls in ERROR_TAXONOMY}
    assert codes == {
        "FilmAnalyserError": 1,
        "InputError": 2,
        "DecodeError": 3,
        "ModelError": 4,
        "StorageError": 5,
        "AnalysisError": 6,
    }


def test_resource_error_is_an_internal_error() -> None:
    assert ResourceError.exit_code == FilmAnalyserError.exit_code == 1


def test_exit_codes_and_message_keys_are_unique() -> None:
    assert len({c.exit_code for c in ERROR_TAXONOMY}) == len(ERROR_TAXONOMY)
    assert len({c.message_key for c in ERROR_TAXONOMY}) == len(ERROR_TAXONOMY)


def test_error_carries_detail() -> None:
    with pytest.raises(InputError, match="bad path"):
        raise InputError("bad path")
