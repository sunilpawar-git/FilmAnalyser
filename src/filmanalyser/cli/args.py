"""Argument parsing: the command line becomes one frozen `Options` value. No analysis, no I/O."""

import argparse
from collections.abc import Sequence
from dataclasses import dataclass
from importlib.metadata import version as installed_version
from pathlib import Path

from filmanalyser.pipeline.runner import default_model_dir
from filmanalyser.report.resources.layout import DEFAULT_OUT_SUFFIX, PACKAGE_NAME, REPORT_FILE
from filmanalyser.report.resources.strings import Strings


@dataclass(frozen=True)
class Options:
    film: Path
    out: Path
    report: Path
    fresh: bool
    verbose: bool
    separate_voices: bool
    separation_model: str


def _parser(strings: Strings) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=strings.text("cli.prog"), description=strings.text("app.tagline")
    )
    parser.add_argument(strings.text("cli.arg_film"), help=strings.text("cli.help_film"))
    parser.add_argument("--out", help=strings.text("cli.help_out"))
    parser.add_argument("--report", help=strings.text("cli.help_report"))
    parser.add_argument("--fresh", action="store_true", help=strings.text("cli.help_fresh"))
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
    parser.add_argument(
        "--version",
        action="version",
        version=strings.text(
            "cli.version", name=PACKAGE_NAME, version=installed_version(PACKAGE_NAME)
        ),
    )
    return parser


def parse_args(argv: Sequence[str] | None, strings: Strings) -> Options:
    """The options for one run. `--help` and `--version` exit here (argparse's own SystemExit);
    a usage error exits with code 2, which is also the input-error code."""
    args = _parser(strings).parse_args(argv)
    film = Path(args.film)
    out = Path(args.out) if args.out else Path(f"{film.stem}{DEFAULT_OUT_SUFFIX}")
    return Options(
        film=film,
        out=out,
        report=Path(args.report) if args.report else out / REPORT_FILE,
        fresh=args.fresh,
        verbose=args.verbose,
        separate_voices=args.separate_voices,
        separation_model=args.separation_model,
    )
