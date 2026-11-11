"""Input path validation, tool lookup and stderr scrubbing: the boundary before any subprocess.

Every path that reaches ffmpeg/ffprobe comes out of `validate_input_path`, which returns an
absolute, symlink-resolved path to a readable regular file. An absolute path starts with `/`,
so it can never be read as an option, whatever the file is called.
"""

import os
import shutil
from pathlib import Path

from filmanalyser.core.errors import DecodeError, InputError


def _name_of(text: str) -> str:
    """Only the basename ever goes into an error (never a full path); control chars removed."""
    return os.path.basename(text).replace("\x00", "?")


def _fail(key: str, text: str) -> InputError:
    return InputError(key=f"error.input.{key}", name=_name_of(text))


def validate_input_path(raw: str | os.PathLike[str]) -> Path:
    """Resolve `raw` and require an existing, readable, regular file."""
    text = os.fspath(raw)
    if not text.strip() or "\x00" in text:
        raise _fail("invalid_path", text)
    try:
        path = Path(text).resolve(strict=True)
    except FileNotFoundError:
        raise _fail("not_found", text) from None
    except PermissionError:
        raise _fail("unreadable", text) from None
    except (OSError, RuntimeError):  # symlink loop, name too long, ...
        raise _fail("invalid_path", text) from None
    if not path.is_file():
        raise _fail("not_a_file", text)
    if not os.access(path, os.R_OK):
        raise _fail("unreadable", text)
    return path


def find_tool(name: str) -> str:
    """Absolute location of an external tool on PATH, or a DecodeError that names it."""
    found = shutil.which(name)
    if found is None:
        raise DecodeError(key="error.decode.tool_missing", tool=name)
    return found


def scrub_stderr(raw: bytes, path: Path, limit: int) -> str:
    """Bounded, printable tool output with the film's full path reduced to its basename."""
    text = raw.decode("utf-8", errors="replace").replace(str(path), path.name)
    return text[-limit:].strip()
