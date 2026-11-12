"""View: renders a ReportView into one static HTML page (DECISIONS #52, #56).

Jinja2 with autoescape on, so every value is escaped by default. The template receives the text
lookup `t` (strings.toml), the colour tokens as CSS (colors.toml) and the view. It contains no
logic beyond loops and lookups.
"""

import jinja2

from filmanalyser.report.resources.colors import ColorTokens
from filmanalyser.report.resources.layout import TEMPLATE, TEMPLATE_DIR, TEMPLATE_PACKAGE
from filmanalyser.report.resources.strings import Strings
from filmanalyser.report.viewmodel import ReportView


def _environment() -> jinja2.Environment:
    return jinja2.Environment(
        loader=jinja2.PackageLoader(TEMPLATE_PACKAGE, TEMPLATE_DIR),
        autoescape=True,
        undefined=jinja2.StrictUndefined,  # a misspelt name fails the render, never prints blank
    )


def render_report(view: ReportView, strings: Strings, colors: ColorTokens) -> str:
    template = _environment().get_template(TEMPLATE)
    return template.render(view=view, t=strings.text, css=colors.css())
