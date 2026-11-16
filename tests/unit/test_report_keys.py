"""Every key the view model can produce resolves in strings.toml (a template looks it up at render
time, and a missing one would only fail on the film that reaches it)."""

import pytest

from filmanalyser.analysis.flags import FlagKind
from filmanalyser.analysis.tension import COMPONENTS
from filmanalyser.core import features as f
from filmanalyser.report.resources.keys import feature_key, flag_kind_key, flag_value_key
from filmanalyser.report.resources.strings import Strings

KEYS = Strings.load().keys()


@pytest.mark.parametrize("kind", list(FlagKind))
def test_every_flag_kind_has_a_label_and_a_value_sentence(kind: FlagKind) -> None:
    assert flag_kind_key(kind) in KEYS
    assert "$value" in Strings.load().table[flag_value_key(kind)]


@pytest.mark.parametrize("name", [*f.STATE_FEATURES, *COMPONENTS, "tension"])
def test_every_feature_the_report_names_has_a_label(name: str) -> None:
    assert feature_key(name) in KEYS


@pytest.mark.parametrize(
    "key",
    [
        "act.audio.used",
        "act.audio.not_used",
        "act.zone.found",
        "act.zone.empty",
        "act.zone.too_short",
        "chart.mark.break",
        "chart.mark.peak",
        "chart.mark.plateau",
        *(
            f"chart.{n}.{part}"
            for n in ("cut_rate", "tension", "loudness", "mix", "picture")
            for part in ("label", "caption")
        ),
    ],
)
def test_every_fixed_key_resolves(key: str) -> None:
    assert key in KEYS


def test_the_zone_sentences_name_what_the_reader_needs() -> None:
    text = Strings.load().text
    assert (
        text("act.zone.too_short", zone=1, needs="13:00")
        == "Zone 1: too short to judge (needs 13:00)."
    )
    assert text("act.zone.empty", zone=2) == "Zone 2: no shift found."
