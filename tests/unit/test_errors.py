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


def test_error_defaults_to_its_category_key() -> None:
    err = DecodeError()
    assert err.key == DecodeError.message_key
    assert err.fields == {}


def test_error_carries_a_specific_key_and_fields_without_english_text() -> None:
    err = InputError(key="error.input.not_found", name="film.mp4")
    assert err.key == "error.input.not_found"
    assert err.fields == {"name": "film.mp4"}
    assert str(err) == "error.input.not_found name=film.mp4"
    assert err.exit_code == 2  # the category still owns the exit code


def test_detail_text_is_kept_next_to_the_key() -> None:
    err = DecodeError("ffmpeg said no", key="error.decode.ffmpeg_failed", code=1)
    assert str(err) == "error.decode.ffmpeg_failed code=1: ffmpeg said no"
