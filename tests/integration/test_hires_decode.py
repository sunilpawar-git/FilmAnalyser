"""Loudness and true peak are measured on a 48 kHz window; speech stays on 16 kHz (DECISIONS #72).
A chunk carries both windows, over the same span, and the measured tone matches its 48 kHz reference
(the standard's rate) more closely than the 16 kHz decode ever could."""

from pathlib import Path

import numpy as np

from filmanalyser.core.config import AUDIO_HIRES_RATE, AUDIO_RATE, Config
from filmanalyser.extractors._kweighting import biquads
from filmanalyser.extractors.loudness import EXTRACTOR
from filmanalyser.media.audio import audio_stream
from filmanalyser.media.ffmpeg_stream import decode_chunks
from tests.fixtures.make_synthetic import make_av_clip
from tests.unit.test_loudness import _gain_db

TONE = "0.5*sin(2*PI*440*t)*between(t\\,2\\,4)"
CONFIG = Config(chunk_seconds=2.0, overlap_seconds=0.5, analysis_fps=12.0, frame_width=64)


def _tone_reference() -> float:
    """BS.1770 for this tone at 48 kHz (K-weighting at 440 Hz from the published coefficients)."""
    k_db = sum(_gain_db(stage, 440.0, 48000) for stage in biquads(48000))
    return float(-0.691 + k_db + 10 * np.log10(0.5**2 / 2))


def test_a_chunk_carries_both_windows_over_the_same_span(tmp_path: Path) -> None:
    clip = make_av_clip(tmp_path / "tone.mp4", 6.0, TONE)
    stream = audio_stream(clip)
    assert stream is not None
    chunk = next(iter(decode_chunks(clip, CONFIG, channels=1, audio_start_s=stream.start_s)))
    assert chunk.audio is not None and chunk.audio_hires is not None
    assert chunk.audio.rate == AUDIO_RATE
    assert chunk.audio_hires.rate == AUDIO_HIRES_RATE
    assert chunk.audio_hires.start_s == chunk.audio.start_s == chunk.first_frame_s
    assert abs(len(chunk.audio_hires.samples) - 2.0 * AUDIO_HIRES_RATE) <= 2  # the first chunk: 2 s


def test_the_measured_tone_matches_its_48_khz_reference(tmp_path: Path) -> None:
    clip = make_av_clip(tmp_path / "tone.mp4", 6.0, TONE)
    stream = audio_stream(clip)
    assert stream is not None
    chunks = list(decode_chunks(clip, CONFIG, channels=1, audio_start_s=stream.start_s))
    tone = chunks[1]  # core 2 to 4 s: the whole tone
    measured = EXTRACTOR.extract(tone)["integrated_lufs"]
    assert abs(measured - _tone_reference()) < 0.05
