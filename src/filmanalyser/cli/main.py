"""Command line: `filmanalyser FILM --out DIR [--report FILE] [-v]` (DECISIONS #56).

Argument parsing and printing only: the analysis lives in pipeline/, the page in report/. Every
message comes from strings.toml. An expected error prints its message and returns its exit code
(the error taxonomy, core/errors.py); it never prints a traceback.
"""

import argparse
import contextlib
import logging
import sys
from collections.abc import Iterator, Sequence
from pathlib import Path

from filmanalyser.core.config import Config
from filmanalyser.core.errors import FilmAnalyserError
from filmanalyser.core.events import LOG_FORMAT, LOGGER
from filmanalyser.pipeline.runner import analyse, default_model_dir
from filmanalyser.report.renderer import render_report
from filmanalyser.report.resources.colors import ColorTokens
from filmanalyser.report.resources.layout import REPORT_FILE
from filmanalyser.report.resources.strings import Strings
from filmanalyser.report.viewmodel import build_view


def _parser(strings: Strings) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=strings.text("cli.prog"), description=strings.text("app.tagline")
    )
    parser.add_argument(strings.text("cli.arg_film"), help=strings.text("cli.help_film"))
    parser.add_argument("--out", required=True, help=strings.text("cli.help_out"))
    parser.add_argument("--report", help=strings.text("cli.help_report"))
    parser.add_argument(
        "--separate-voices", action="store_true", help=strings.text("cli.help_separate_voices")
    )
    parser.add_argument(
        "--separation-model",
        default=str(default_model_dir()),
        help=strings.text("cli.help_separation_model"),
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help=strings.text("cli.help_verbose")
    )
    return parser


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


def _run(args: argparse.Namespace, strings: Strings) -> int:
    film, out = Path(args.film), Path(args.out)
    report = Path(args.report) if args.report else out / REPORT_FILE
    config = Config(separate_voices=args.separate_voices, separation_model=args.separation_model)
    store = analyse(film, out, config)
    view = build_view(store.read_columns(), film=film.name)
    report.write_text(render_report(view, strings, ColorTokens.load()), encoding="utf-8")
    message = strings.text("cli.done", film=film.name, cuts=view.total_cuts, report=report.name)
    print(message)
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    strings = Strings.load()
    args = _parser(strings).parse_args(argv)
    try:
        with _events_to_stderr(args.verbose):
            return _run(args, strings)
    except FilmAnalyserError as exc:
        print(strings.text(exc.key, **exc.fields), file=sys.stderr)
        return exc.exit_code
