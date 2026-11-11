"""Error taxonomy. Each category maps to a stable CLI exit code and a strings.toml message key."""


class FilmAnalyserError(Exception):
    """Base class: unexpected or internal failures. Exit code 1.

    User-facing text never lives in the exception: `key` names an entry in strings.toml (the
    category default unless a specific key is given) and `fields` fill its `$placeholders`.
    `detail` is optional developer diagnostics for logs. Fields must be basenames, never paths.
    """

    exit_code = 1
    message_key = "error.internal.default"

    def __init__(self, detail: str = "", *, key: str | None = None, **fields: str | int | float):
        self.key = key or self.message_key
        self.fields = fields
        text = self.key + "".join(f" {name}={value}" for name, value in fields.items())
        super().__init__(f"{text}: {detail}" if detail else text)


class InputError(FilmAnalyserError):
    """The user supplied something invalid (path, option, configuration value)."""

    exit_code = 2
    message_key = "error.input.default"


class DecodeError(FilmAnalyserError):
    """The media could not be decoded."""

    exit_code = 3
    message_key = "error.decode.default"


class ModelError(FilmAnalyserError):
    """A model file is missing, tampered with, or failed to run."""

    exit_code = 4
    message_key = "error.model.default"


class StorageError(FilmAnalyserError):
    """The feature store or resume manifest is unreadable, corrupt or mismatched."""

    exit_code = 5
    message_key = "error.storage.default"


class AnalysisError(FilmAnalyserError):
    """Timeline analysis could not complete."""

    exit_code = 6
    message_key = "error.analysis.default"


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
