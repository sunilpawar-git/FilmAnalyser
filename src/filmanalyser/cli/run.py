"""One run, wired: check the paths, (optionally) clear the store, analyse, build the view, render,
write the report. No rules of its own: each step belongs to the layer that is called."""

from pathlib import Path

from filmanalyser.cli.args import Options
from filmanalyser.core.config import Config
from filmanalyser.core.errors import InputError
from filmanalyser.pipeline.runner import analyse, validate_input_path
from filmanalyser.report.renderer import render_report
from filmanalyser.report.resources.colors import ColorTokens
from filmanalyser.report.resources.strings import Strings
from filmanalyser.report.viewmodel import build_view
from filmanalyser.storage.files import open_directory, write_atomic
from filmanalyser.storage.reset import clear_store


def check_report_path(report: Path, film: Path) -> None:
    """Refuse a report path that would overwrite the film or go through a link, or whose folder
    is missing. Checked before the analysis starts: a run can take most of an hour."""
    name = report.name
    if report.resolve() == film:
        raise InputError(key="error.input.report_is_film", name=name)
    if report.is_symlink() or not report.parent.is_dir():
        raise InputError(key="error.input.report_unwritable", name=name)


def run(options: Options, strings: Strings, config: Config | None = None) -> str:
    """Analyse the film and write its report; returns the line to print. `config` defaults to the
    settings the options imply (tests pass a small chunk size)."""
    film = validate_input_path(options.film)
    open_directory(options.out)  # the default report lives there
    check_report_path(options.report, film)
    settings = config or Config(
        separate_voices=options.separate_voices, separation_model=options.separation_model
    )
    if options.fresh:
        clear_store(options.out)
    store = analyse(film, options.out, settings)
    view = build_view(store.read_columns(), film=film.name)
    page = render_report(view, strings, ColorTokens.load())
    write_atomic(options.report.parent.resolve(), options.report.name, page.encode("utf-8"))
    return strings.text(
        "cli.done", film=film.name, cuts=view.overview.total_cuts, report=options.report.name
    )
