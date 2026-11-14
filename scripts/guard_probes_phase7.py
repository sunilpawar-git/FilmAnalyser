"""Phase 7 guards (the report): planted violations of the template and view-model rules, and
mutations of the honesty rules (a zone too short to judge, the sound statement, the unvalidated
notice, escaping, the CSP) that a named test must catch."""

from guard_probes import PROBE, Probe, _arch, _mutation, _probe

REPORT = "src/filmanalyser/report"
TEMPLATES = _arch("test_report_templates.py")
VIEWMODEL = f"{REPORT}/viewmodel.py"
PAGE = f"{REPORT}/templates/report.html"
UNIT = "tests/unit"


def _template(name: str, html: str) -> Probe:
    return Probe(
        name,
        f"{REPORT}/templates/partials/{PROBE}.html",
        html,
        TEMPLATES,
        PROBE,
    )


def phase7_probes() -> list[Probe]:
    layers = _arch("test_layer_imports.py")
    return [
        _template("template runs a script", "<script>run()</script>\n"),
        _template("template links an external address", "<p>https://example.test/x</p>\n"),
        _template("template has an inline style", '<p style="color: red">x</p>\n'),
        _template("template has an event handler", '<p onclick="run()">x</p>\n'),
        _template(
            "template uses an undefined colour token", "<style>p { color: var(--nope); }</style>\n"
        ),
        _template("template imports a stylesheet", "<style>@import 'x.css';</style>\n"),
        Probe(
            "view model part reads a file",
            f"{REPORT}/viewmodel_{PROBE}.py",
            "import pathlib\n",
            layers,
            PROBE,
        ),
        _probe(
            "view imports analysis",
            "report",
            "from filmanalyser.analysis import timeline\n",
            layers,
        ),
        _probe(
            "plain English in the report code",
            "report",
            'NOTE = "No break found"\n',
            _arch("test_no_hardcoded_strings.py"),
        ),
    ]


def phase7_mutation_probes() -> list[Probe]:
    return [*_layer_mutations(), *_viewmodel_mutations(), *_page_mutations()]


def _layer_mutations() -> list[Probe]:
    return [
        _mutation(
            "chart geometry reads a file",
            f"{REPORT}/charts.py",
            ("import numpy as np\n", "import numpy as np\nimport pathlib\n"),
            _arch("test_layer_imports.py")[-1],
            "test_real_tree_respects_layering",
        ),
    ]


def _viewmodel_mutations() -> list[Probe]:
    return [
        _mutation(
            "a zone too short to judge reads as no break",
            VIEWMODEL,
            (
                'ZoneView(number, "act.zone.too_short", "", needs)',
                'ZoneView(number, "act.zone.empty", "", "")',
            ),
            f"{UNIT}/test_viewmodel.py",
            "test_a_zone_a_short_film_cannot_judge_is_not_called_empty",
        ),
        _mutation(
            "the sound statement always says sound was used",
            VIEWMODEL,
            ('"act.audio.used" if acts.audio_used else "act.audio.not_used"', '"act.audio.used"'),
            f"{UNIT}/test_viewmodel.py",
            "test_the_act_section_states_whether_audio_was_used",
        ),
    ]


def _page_mutations() -> list[Probe]:
    return [
        _mutation(
            "the unvalidated notice is left off the page",
            PAGE,
            ("{% include 'partials/notice.html' %}", ""),
            f"{UNIT}/test_renderer.py",
            "test_the_unvalidated_notice_is_on_the_page",
        ),
        _mutation(
            "the page escapes nothing",
            f"{REPORT}/renderer.py",
            ("autoescape=True", "autoescape=False"),
            f"{UNIT}/test_renderer.py",
            "test_the_film_name_is_escaped_not_injected",
        ),
        _mutation(
            "a flag is shown without its timestamp",
            VIEWMODEL,
            ("start_text=clock_text(flag.start_s),", 'start_text="",'),
            f"{UNIT}/test_viewmodel.py",
            "test_every_flag_carries_a_timestamp_a_rule_and_a_value",
        ),
    ]
