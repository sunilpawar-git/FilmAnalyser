"""Error taxonomy. Each category maps to a stable CLI exit code and a strings.toml message key."""


class FilmAnalyserError(Exception):
    """Base class: unexpected or internal failures. Exit code 1."""

    exit_code = 1
    message_key = "error.internal"


class InputError(FilmAnalyserError):
    """The user supplied something invalid (path, option, configuration value)."""

    exit_code = 2
    message_key = "error.input"


class DecodeError(FilmAnalyserError):
    """The media could not be decoded."""

    exit_code = 3
    message_key = "error.decode"


class ModelError(FilmAnalyserError):
    """A model file is missing, tampered with, or failed to run."""

    exit_code = 4
    message_key = "error.model"


class StorageError(FilmAnalyserError):
    """The feature store or resume manifest is unreadable, corrupt or mismatched."""

    exit_code = 5
    message_key = "error.storage"


class AnalysisError(FilmAnalyserError):
    """Timeline analysis could not complete."""

    exit_code = 6
    message_key = "error.analysis"


class ResourceError(FilmAnalyserError):
    """A packaged resource (strings.toml / colors.toml) is missing or malformed: a build bug."""


# SSOT: the categories that own a distinct exit code and message.
ERROR_TAXONOMY: tuple[type[FilmAnalyserError], ...] = (
    FilmAnalyserError,
    InputError,
    DecodeError,
    ModelError,
    StorageError,
    AnalysisError,
)
