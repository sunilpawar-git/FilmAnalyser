"""The four analyses of one fixed synthetic film, pinned to a stored answer. A change to any rule
or threshold that moves the answer fails here and must be a reviewed change to the golden file."""

import json
from dataclasses import asdict, is_dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from filmanalyser.analysis.act_breaks import find_act_breaks
from filmanalyser.analysis.flags import find_flags
from filmanalyser.analysis.pacing import analyse_pacing
from filmanalyser.analysis.tension import analyse_tension
from filmanalyser.analysis.timeline import build_timeline
from tests.fixtures.timelines import golden_film

GOLDEN = Path(__file__).resolve().parents[1] / "golden" / "analysis_tent_film.json"
DIGITS = 6


def plain(value: Any) -> Any:
    """JSON-ready: dataclasses to dicts, tuples to lists, enums to values, floats rounded."""
    if is_dataclass(value) and not isinstance(value, type):
        return plain(asdict(value))
    if isinstance(value, dict):
        return {key: plain(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [plain(item) for item in value]
    if isinstance(value, Enum):
        return value.value
    return round(value, DIGITS) if isinstance(value, float) else value


def analyses() -> dict[str, Any]:
    timeline = build_timeline(golden_film())
    answer: dict[str, Any] = plain(
        {
            "act_breaks": find_act_breaks(timeline),
            "tension": analyse_tension(timeline),
            "pacing": analyse_pacing(timeline),
            "flags": find_flags(timeline),
        }
    )
    return answer


def test_the_analyses_of_the_tent_film_match_the_golden_file() -> None:
    assert analyses() == json.loads(GOLDEN.read_text(encoding="utf-8"))


def test_the_golden_film_has_something_for_every_analysis_to_report() -> None:
    got = analyses()
    assert len(got["act_breaks"]["breaks"]) == 2
    assert got["tension"]["peak"] is not None
    assert got["pacing"]["plateaus"] != []
    assert {flag["kind"] for flag in got["flags"]} >= {"fast_cutting", "quiet", "clipping"}
