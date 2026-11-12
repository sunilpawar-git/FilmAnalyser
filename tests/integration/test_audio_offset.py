"""Sound and picture stay aligned when the audio track starts at a different time from the picture
(DECISIONS #67). The tone sits at 0 to 1 s of the audio clock. The audio is delayed by 0.5 s on the
container clock, so the tone must land at 0.5 to 1.5 s of film time, with silence filling the lead.

The control: without the audio start, the same window reads the tone at 0 s (the first sample the
track has), which is 0.5 s early. That is the error this test exists to prevent."""

from pathlib import Path

import numpy as np
import pytest

from filmanalyser.core.config import AUDIO_RATE, Config
from filmanalyser.media.audio import audio_stream
from filmanalyser.media.ffmpeg_stream import decode_chunks
from tests.fixtures.make_synthetic import make_av_clip

TONE = "0.5*sin(2*PI*440*t)*between(t\\,0\\,1)"  # 440 Hz from 0 s to 1 s of the audio clock
DELAY_S = 0.5
CONFIG = Config(chunk_seconds=2.0, overlap_seconds=0.5, analysis_fps=12.0, frame_width=64)
TOLERANCE_SAMPLES = 2


@pytest.fixture(scope="module")
def delayed_clip(tmp_path_factory: pytest.TempPathFactory) -> Path:
    path = tmp_path_factory.mktemp("offset") / "delayed.mp4"
    return make_av_clip(path, 6.0, TONE, audio_offset=DELAY_S)


def _first_loud(samples: np.ndarray) -> int:
    loud = np.flatnonzero(np.abs(samples[:, 0]) > 0.05)
    assert loud.size, "no tone in this window"
    return int(loud[0])


def test_the_probe_reports_the_audio_start(delayed_clip: Path) -> None:
    stream = audio_stream(delayed_clip)
    assert stream is not None
    assert abs(stream.start_s - DELAY_S) < 0.01


def test_the_tone_lands_where_the_container_clock_puts_it(delayed_clip: Path) -> None:
    stream = audio_stream(delayed_clip)
    assert stream is not None
    first = next(
        iter(decode_chunks(delayed_clip, CONFIG, channels=1, audio_start_s=stream.start_s))
    )
    assert first.audio is not None
    # the window is film 0 to 2 s; the tone starts at film 0.5 s = 8000 samples in
    assert abs(_first_loud(first.audio.samples) - 0.5 * AUDIO_RATE) <= TOLERANCE_SAMPLES


def test_silence_fills_the_lead_before_the_audio_starts(delayed_clip: Path) -> None:
    stream = audio_stream(delayed_clip)
    assert stream is not None
    first = next(
        iter(decode_chunks(delayed_clip, CONFIG, channels=1, audio_start_s=stream.start_s))
    )
    assert first.audio is not None
    lead = first.audio.samples[: round(DELAY_S * AUDIO_RATE) - TOLERANCE_SAMPLES]
    assert float(np.max(np.abs(lead))) < 1e-4


def test_ignoring_the_offset_would_put_the_tone_half_a_second_early(delayed_clip: Path) -> None:
    early = next(iter(decode_chunks(delayed_clip, CONFIG, channels=1, audio_start_s=0.0)))
    assert early.audio is not None
    assert abs(_first_loud(early.audio.samples)) <= TOLERANCE_SAMPLES


def test_a_track_that_starts_after_the_film_is_silent_throughout(delayed_clip: Path) -> None:
    """A track starting at 100 s, far past this 6 s film: every window is lead silence."""
    chunks = list(decode_chunks(delayed_clip, CONFIG, channels=1, audio_start_s=100.0))
    assert chunks and all(c.audio is not None for c in chunks)
    assert all(float(np.max(np.abs(c.audio.samples))) == 0.0 for c in chunks if c.audio)
