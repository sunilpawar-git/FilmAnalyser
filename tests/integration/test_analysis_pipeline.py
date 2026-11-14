"""Timeline analysis on features the pipeline really stored: a synthetic film whose sound is known
by construction (silence, then a tone from 12 s to 28 s, then silence), 1 s chunks."""

from pathlib import Path

from filmanalyser.analysis.act_breaks import ActSettings, find_act_breaks
from filmanalyser.analysis.flags import find_flags
from filmanalyser.analysis.pacing import analyse_pacing
from filmanalyser.analysis.tension import analyse_tension
from filmanalyser.analysis.timeline import Columns, build_timeline
from filmanalyser.core.config import Config
from filmanalyser.pipeline.runner import analyse
from tests.fixtures.make_synthetic import make_av_clip, make_silent_clip

CONFIG = Config(chunk_seconds=1.0, overlap_seconds=0.25, analysis_fps=12.0, frame_width=64)
TONE = "0.5*sin(2*PI*440*t)*between(t\\,12\\,28)"
SECONDS = 40.0
# Only the sound changes here and the picture is still, so most of the nine features sit at zero
# and the score is diluted by them (DECISIONS #90). The default threshold is for films whose
# picture and sound move together; this check is about the path from the store to the answer.
LOW_SCORE = 0.8


def _columns(film: Path, out: Path) -> Columns:
    return analyse(film, out, CONFIG).read_columns()


def test_the_stored_features_give_breaks_where_the_sound_changes(tmp_path: Path) -> None:
    columns = _columns(
        make_av_clip(tmp_path / "av.mp4", SECONDS, TONE, flat=True), tmp_path / "store"
    )
    result = find_act_breaks(build_timeline(columns), ActSettings(min_score=LOW_SCORE))
    assert result.audio_used is True
    first, second = (
        result.breaks
    )  # the tone's stop rings for 50 ms, so the second may be a chunk late
    assert first.boundary == 12 and second.boundary in (28, 29)
    assert (first.time_s, second.time_s) == (12.0, float(second.boundary))
    assert len(result.acts) == 3 and result.acts[-1].end_s == SECONDS


def test_the_other_analyses_run_on_the_same_stored_features(tmp_path: Path) -> None:
    timeline = build_timeline(
        _columns(make_av_clip(tmp_path / "av.mp4", SECONDS, TONE, flat=True), tmp_path / "store")
    )
    pacing = analyse_pacing(timeline)
    assert len(pacing.rate_per_min) == timeline.count == 40
    assert analyse_tension(timeline).components == tuple(analyse_tension(timeline).components)
    assert all(flag.end_s > flag.start_s for flag in find_flags(timeline))


def test_a_film_without_audio_is_analysed_on_the_picture_alone(tmp_path: Path) -> None:
    columns = _columns(make_silent_clip(tmp_path / "silent.mp4", SECONDS), tmp_path / "store")
    timeline = build_timeline(columns)
    result = find_act_breaks(timeline)
    assert result.audio_used is False
    assert result.breaks == ()
    assert analyse_tension(timeline).components == ("cut_rate",)


def test_a_film_shorter_than_two_windows_is_analysed_without_error(tmp_path: Path) -> None:
    columns = _columns(make_av_clip(tmp_path / "av.mp4", 6.0, TONE), tmp_path / "store")
    timeline = build_timeline(columns)
    assert find_act_breaks(timeline).breaks == ()
    assert find_act_breaks(timeline).scored == 0


def test_the_analysis_of_a_stored_film_is_the_same_every_time(tmp_path: Path) -> None:
    film = make_av_clip(tmp_path / "av.mp4", SECONDS, TONE, flat=True)
    first = find_act_breaks(build_timeline(_columns(film, tmp_path / "a")))
    second = find_act_breaks(build_timeline(_columns(film, tmp_path / "b")))
    assert first == second
