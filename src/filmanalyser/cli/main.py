"""The command: `filmanalyser FILM [--out DIR] [--report FILE] [--fresh] [-v]` (DECISIONS #56).

Entry point and error mapping only. An expected error prints its message from strings.toml and
returns its taxonomy exit code (core/errors.py); an interrupt returns 130; anything unexpected
returns 1 with a plain message. None of them prints a traceback unless -v asks for one.
"""

import contextlib
import logging
import sys
import traceback
from collections.abc import Iterator, Sequence

from filmanalyser.cli.args import parse_args
from filmanalyser.cli.run import run
from filmanalyser.core.errors import EXIT_INTERRUPTED, FilmAnalyserError
from filmanalyser.core.events import LOG_FORMAT, LOGGER
from filmanalyser.report.resources.strings import Strings


@contextlib.contextmanager
def _events_to_stderr(verbose: bool) -> Iterator[None]:
    """With -v, the structured events go to stderr for this command only: the handler and the
    level are restored on exit, so the library's logger is never left configured (a leaked handler
    would write to a closed stream in the next caller)."""
    if not verbose:
        yield
        return
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter(LOG_FORMAT))
    previous = LOGGER.level
    LOGGER.addHandler(handler)
    LOGGER.setLevel(logging.INFO)
    try:
        yield
    finally:
        LOGGER.removeHandler(handler)
        LOGGER.setLevel(previous)


def _printable(text: str) -> str:
    """A message with every control character (a terminal escape in a file name, a newline)
    replaced, so a film's name cannot rewrite the screen or forge a second line."""
    return "".join(ch if ch.isprintable() else "?" for ch in text)


def main(argv: Sequence[str] | None = None) -> int:
    strings = Strings.load()
    options = parse_args(argv, strings)
    try:
        with _events_to_stderr(options.verbose):
            print(_printable(run(options, strings)))
            return 0
    except FilmAnalyserError as exc:
        print(_printable(strings.text(exc.key, **exc.fields)), file=sys.stderr)
        return exc.exit_code
    except KeyboardInterrupt:
        print(strings.text("cli.interrupted"), file=sys.stderr)
        return EXIT_INTERRUPTED
    except Exception:  # the last line of defence: a message, not a traceback (unless -v)
        print(strings.text(FilmAnalyserError.message_key), file=sys.stderr)
        if options.verbose:
            traceback.print_exc()
        return FilmAnalyserError.exit_code
