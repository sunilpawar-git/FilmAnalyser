"""ViewModel: stored columns in, display-ready values out (EXECUTION_PLAN section 0, DECISIONS #28).

Pure: no I/O, no locale, no resource reads. It runs the analysis and turns the results into what the
view shows: values written as text with a point and a colon (display.py), keys that name the words
(strings.toml holds them), and chart geometry (viewmodel_charts.py). The view only loops over these
values and looks up their labels. Everything here is an observation: none of the analysis is
validated against real films (DECISIONS #94).
"""

from dataclasses import dataclass

import numpy as np

from filmanalyser.analysis.act_breaks import ZONES, ActBreak, ActBreaks, find_act_breaks
from filmanalyser.analysis.flags import Flag, FlagKind, find_flags
from filmanalyser.analysis.pacing import Pacing, analyse_pacing
from filmanalyser.analysis.tension import Tension, analyse_tension
from filmanalyser.analysis.timeline import Columns, Timeline, build_timeline
from filmanalyser.core import features as f
from filmanalyser.core.config import TENSION_MIN_PEAK_Z
from filmanalyser.report.charts import Chart
from filmanalyser.report.display import clock_text, number_text
from filmanalyser.report.palette_view import PaletteView, build_palette
from filmanalyser.report.resources.keys import feature_key, flag_kind_key, flag_value_key
from filmanalyser.report.viewmodel_charts import build_charts

_PERCENT = 100.0
_FLAG_DECIMALS = {  # decimals of the value each kind of flag carries
    FlagKind.FAST_CUTTING: 1,
    FlagKind.LOUD: 1,
    FlagKind.QUIET: 2,
    FlagKind.CLIPPING: 1,
    FlagKind.LONG_TAKE: 0,
}


@dataclass(frozen=True)
class Overview:
    total_cuts: int
    average_shot_text: str  # seconds
    mean_rate_text: str  # cuts and gradual transitions per minute


@dataclass(frozen=True)
class BreakView:
    time_text: str
    percent_text: str  # share of the film
    score_text: str
    moved_keys: tuple[str, ...]


@dataclass(frozen=True)
class ZoneView:
    number: int
    key: str  # act.zone.found | act.zone.empty | act.zone.too_short
    time_text: str  # the break, when there is one
    needs_text: str  # the film length that would be needed to judge the zone


@dataclass(frozen=True)
class SpanView:
    number: int
    start_text: str
    end_text: str


@dataclass(frozen=True)
class ActsView:
    audio_key: str  # act.audio.used | act.audio.not_used
    breaks: tuple[BreakView, ...]
    zones: tuple[ZoneView, ...]
    spans: tuple[SpanView, ...]
    feature_keys: tuple[str, ...]


@dataclass(frozen=True)
class PeakView:
    time_text: str
    height_text: str  # standard deviations above the film's mean


@dataclass(frozen=True)
class TensionView:
    peak: PeakView | None
    component_keys: tuple[str, ...]
    min_height_text: str  # the height a peak must reach to be reported


@dataclass(frozen=True)
class PlateauView:
    start_text: str
    end_text: str
    rate_text: str


@dataclass(frozen=True)
class PacingView:
    mean_rate_text: str
    plateaus: tuple[PlateauView, ...]


@dataclass(frozen=True)
class FlagRow:
    kind_key: str  # flag.kind.<kind>: what was flagged
    start_text: str
    end_text: str
    value_key: str  # flag.value.<kind>: a sentence with a $value placeholder
    value_text: str


@dataclass(frozen=True)
class ReportView:
    film: str
    length_text: str
    chunk_count: int
    audio_used: bool
    overview: Overview
    acts: ActsView
    tension: TensionView
    pacing: PacingView
    flags: tuple[FlagRow, ...]
    charts: tuple[Chart, ...]
    palette: PaletteView | None  # None for a store with no palette columns


def _overview(columns: Columns, pacing: Pacing) -> Overview:
    starts = np.asarray(columns[f.START_S], dtype=np.float64)
    ends = np.asarray(columns[f.END_S], dtype=np.float64)
    total = int(np.asarray(columns[f.CUT_COUNT], dtype=np.float64).sum())
    seconds = float(np.max(ends) - np.min(starts)) if starts.size else 0.0
    return Overview(
        total_cuts=total,
        average_shot_text=number_text(seconds / (total + 1) if seconds > 0 else 0.0),
        mean_rate_text=number_text(pacing.mean_rate),
    )


def _break(found: ActBreak, film_s: float) -> BreakView:
    return BreakView(
        time_text=clock_text(found.time_s),
        percent_text=number_text(_PERCENT * found.time_s / film_s, 0),
        score_text=number_text(found.score, 2),
        moved_keys=tuple(feature_key(name) for name in found.moved),
    )


def _zones(acts: ActBreaks) -> tuple[ZoneView, ...]:
    """A zone is found, judged and empty, or too short to judge: three different statements."""
    needs = clock_text(acts.min_film_s) if acts.min_film_s else ""
    found = iter(acts.breaks)  # at most one break per zone, in time order
    views = []
    for number in range(1, len(ZONES) + 1):
        if number in acts.unscored_zones:
            views.append(ZoneView(number, "act.zone.too_short", "", needs))
        elif number in acts.empty_zones:
            views.append(ZoneView(number, "act.zone.empty", "", ""))
        else:
            views.append(ZoneView(number, "act.zone.found", clock_text(next(found).time_s), ""))
    return tuple(views)


def _acts(acts: ActBreaks, film_s: float) -> ActsView:
    return ActsView(
        audio_key="act.audio.used" if acts.audio_used else "act.audio.not_used",
        breaks=tuple(_break(b, film_s) for b in acts.breaks),
        zones=_zones(acts),
        spans=tuple(
            SpanView(n, clock_text(a.start_s), clock_text(a.end_s))
            for n, a in enumerate(acts.acts, 1)
        ),
        feature_keys=tuple(feature_key(name) for name in acts.features_used),
    )


def _tension(tension: Tension) -> TensionView:
    peak = tension.peak
    return TensionView(
        peak=PeakView(clock_text(peak.start_s), number_text(peak.value)) if peak else None,
        component_keys=tuple(feature_key(name) for name in tension.components),
        min_height_text=number_text(TENSION_MIN_PEAK_Z),
    )


def _pacing(pacing: Pacing) -> PacingView:
    return PacingView(
        mean_rate_text=number_text(pacing.mean_rate),
        plateaus=tuple(
            PlateauView(clock_text(p.start_s), clock_text(p.end_s), number_text(p.mean_rate))
            for p in pacing.plateaus
        ),
    )


def _flag(flag: Flag) -> FlagRow:
    return FlagRow(
        kind_key=flag_kind_key(flag.kind),
        start_text=clock_text(flag.start_s),
        end_text=clock_text(flag.end_s),
        value_key=flag_value_key(flag.kind),
        value_text=number_text(flag.value, _FLAG_DECIMALS[flag.kind]),
    )


def _analyse(timeline: Timeline) -> tuple[ActBreaks, Tension, Pacing, tuple[Flag, ...]]:
    return (
        find_act_breaks(timeline),
        analyse_tension(timeline),
        analyse_pacing(timeline),
        find_flags(timeline),
    )


def build_view(columns: Columns, film: str) -> ReportView:
    """The report's values from the store's columns (`FeatureStore.read_columns`)."""
    timeline = build_timeline(columns)
    acts, tension, pacing, flags = _analyse(timeline)
    return ReportView(
        film=film,
        length_text=clock_text(timeline.film_end_s),
        chunk_count=timeline.count,
        audio_used=acts.audio_used,
        overview=_overview(columns, pacing),
        acts=_acts(acts, max(timeline.film_end_s, 1.0)),
        tension=_tension(tension),
        pacing=_pacing(pacing),
        flags=tuple(_flag(flag) for flag in flags),
        charts=build_charts(timeline, acts, tension, pacing),
        palette=build_palette(columns),
    )
