"""The report's charts, assembled from the analysis results (part of the view model: pure).

Which series each chart draws, on which scale, with which breaks, peak and plateaus marked on it.
The geometry itself is `charts.py`; the words are keys into strings.toml.
"""

import numpy as np

from filmanalyser.analysis.act_breaks import ActBreaks
from filmanalyser.analysis.pacing import Pacing
from filmanalyser.analysis.tension import Tension
from filmanalyser.analysis.timeline import Timeline
from filmanalyser.core import features as f
from filmanalyser.report.charts import Chart, Frame, Marker, Notes, Series, Span, build_chart
from filmanalyser.report.display import clock_text
from filmanalyser.report.resources.keys import MARK_BREAK, MARK_PEAK, SERIES_STYLES, feature_key

_MIX = (f.SPEECH_RATIO, f.TONAL_RATIO, f.SILENCE_RATIO)
_PICTURE = f.VIDEO_STATE_COLUMNS
_SHARE = (0.0, 1.0)


def _lines(timeline: Timeline, names: tuple[str, ...]) -> tuple[Series, ...]:
    return tuple(
        Series(feature_key(name), style, timeline.series[name])
        for name, style in zip(names, SERIES_STYLES, strict=False)
    )


def _break_markers(acts: ActBreaks) -> tuple[Marker, ...]:
    return tuple(
        Marker(b.time_s, MARK_BREAK, "chart.mark.break", clock_text(b.time_s)) for b in acts.breaks
    )


def _peak_markers(tension: Tension) -> tuple[Marker, ...]:
    peak = tension.peak
    if peak is None:
        return ()
    return (Marker(peak.start_s, MARK_PEAK, "chart.mark.peak", clock_text(peak.start_s)),)


def _plateaus(pacing: Pacing) -> tuple[Span, ...]:
    return tuple(Span(p.start_s, p.end_s, "chart.mark.plateau") for p in pacing.plateaus)


def _tension_line(tension: Tension) -> Series:
    return Series("feature.tension", SERIES_STYLES[0], np.asarray(tension.values, dtype=np.float64))


def build_charts(
    timeline: Timeline, acts: ActBreaks, tension: Tension, pacing: Pacing
) -> tuple[Chart, ...]:
    """Every chart the film supports, in reading order; none for a film with no chunks. The
    loudness and mix charts are left out for a film without sound."""
    if timeline.count == 0:
        return ()
    frame = Frame((timeline.start_s + timeline.end_s) / 2.0, timeline.film_end_s)
    breaks = _break_markers(acts)
    rate = timeline.series[f.CUT_RATE]
    top = max(float(np.nanmax(rate)) if np.isfinite(rate).any() else 1.0, 1.0)
    charts = [
        build_chart(
            "chart.cut_rate",
            frame,
            _lines(timeline, (f.CUT_RATE,)),
            (0.0, top),
            Notes(breaks, _plateaus(pacing)),
        ),
        build_chart(
            "chart.tension",
            frame,
            (_tension_line(tension),),
            None,
            Notes((*breaks, *_peak_markers(tension))),
        ),
    ]
    if f.LUFS in timeline.series and np.isfinite(timeline.series[f.LUFS]).any():
        charts.append(
            build_chart("chart.loudness", frame, _lines(timeline, (f.LUFS,)), None, Notes(breaks))
        )
    if all(name in timeline.series for name in _MIX):
        charts.append(
            build_chart("chart.mix", frame, _lines(timeline, _MIX), _SHARE, Notes(breaks))
        )
    present = tuple(name for name in _PICTURE if name in timeline.series)
    charts.append(
        build_chart("chart.picture", frame, _lines(timeline, present), None, Notes(breaks))
    )
    return tuple(charts)
