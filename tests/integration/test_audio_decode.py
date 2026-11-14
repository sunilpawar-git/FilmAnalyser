"""Audio through the real decoder: windows land on the film's clock, stereo stays stereo, a film
without audio is reported as such, and chunk audio lines up with chunk frames (overlap included).

Ground truth is built into the clip: silence from 0 to 2 s, a 440 Hz tone from 2 to 4 s, silence
after. A sample is one 16 kHz tick, so alignment is asserted to within two samples (125 us)."""

import subprocess
from pathlib import Path

import numpy as np
import pytest

from filmanalyser.core.chunk import Chunk
from filmanalyser.core.config import AUDIO_RATE, Config
from filmanalyser.core.errors import DecodeError
from filmanalyser.media.audio import PcmFormat, audio_channels, decode_window
from filmanalyser.media.ffmpeg_stream import decode_chunks
from tests.fixtures.make_synthetic import av_clip_argv, make_av_clip, make_silent_clip

TONE = "0.5*sin(2*PI*440*t)*between(t\\,2\\,4)"  # 440 Hz from 2 s to 4 s, silence elsewhere
TOLERANCE_SAMPLES = 2


def _first_loud(samples: np.ndarray) -> int:
    loud = np.flatnonzero(np.abs(samples[:, 0]) > 0.05)
    assert loud.size, "no tone found in the window"
    return int(loud[0])


def test_the_window_starts_on_the_film_clock(tmp_path: Path) -> None:
    clip = make_av_clip(tmp_path / "tone.mp4", 6.0, TONE)
    window = decode_window(clip, 1.5, 2.0, PcmFormat(1, AUDIO_RATE))
    assert window.dtype == np.float32
    assert window.shape[1] == 1
    assert abs(len(window) - 2.0 * AUDIO_RATE) <= TOLERANCE_SAMPLES
    # the tone starts at film time 2.0 s, which is 0.5 s (8000 samples) into this window
    assert abs(_first_loud(window) - 0.5 * AUDIO_RATE) <= TOLERANCE_SAMPLES


def test_silence_in_the_window_is_silent(tmp_path: Path) -> None:
    clip = make_av_clip(tmp_path / "tone.mp4", 6.0, TONE)
    window = decode_window(clip, 0.0, 1.5, PcmFormat(1, AUDIO_RATE))
    assert float(np.max(np.abs(window))) < 1e-4


def test_stereo_keeps_its_two_channels(tmp_path: Path) -> None:
    clip = make_av_clip(tmp_path / "left.mp4", 4.0, f"{TONE}|0*t", stereo=True)
    assert audio_channels(clip) == 2
    window = decode_window(clip, 2.0, 1.0, PcmFormat(2, AUDIO_RATE))
    assert window.shape[1] == 2
    assert float(np.max(np.abs(window[:, 0]))) > 0.1  # the left channel carries the tone
    assert float(np.max(np.abs(window[:, 1]))) < 1e-4  # the right channel is silent


def test_a_mono_clip_reports_one_channel(tmp_path: Path) -> None:
    assert audio_channels(make_av_clip(tmp_path / "m.mp4", 2.0, TONE)) == 1


def test_a_film_without_audio_reports_no_channels(tmp_path: Path) -> None:
    assert audio_channels(make_silent_clip(tmp_path / "silent.mp4", 2.0)) is None


def test_chunk_audio_lines_up_with_chunk_frames_including_overlap(tmp_path: Path) -> None:
    clip = make_av_clip(tmp_path / "tone.mp4", 6.0, TONE)
    config = Config(chunk_seconds=2.0, overlap_seconds=0.5)  # 24 frames, 6 frames of overlap
    chunks = list(decode_chunks(clip, config, channels=1))
    assert len(chunks) >= 3
    second = chunks[1]  # core 2.0 s .. 4.0 s; its window starts 0.5 s earlier, at 1.5 s
    assert isinstance(second, Chunk) and second.audio is not None
    assert second.audio.start_s == second.first_frame_s == 1.5
    assert second.audio_core_offset == round(0.5 * AUDIO_RATE)
    # the tone starts at the first sample of the core: 0.5 s into the window
    assert abs(_first_loud(second.audio.samples) - 0.5 * AUDIO_RATE) <= TOLERANCE_SAMPLES
    assert abs(len(second.core_audio) - 2.0 * AUDIO_RATE) <= TOLERANCE_SAMPLES


def test_decoding_without_channels_attaches_no_audio(tmp_path: Path) -> None:
    clip = make_av_clip(tmp_path / "tone.mp4", 2.0, TONE)
    chunks = list(decode_chunks(clip, Config(chunk_seconds=1.0, overlap_seconds=0.0)))
    assert chunks and all(chunk.audio is None for chunk in chunks)


def test_a_file_that_is_not_media_is_refused_by_the_probe(tmp_path: Path) -> None:
    not_media = tmp_path / "notes.mp4"
    not_media.write_text("this is text, not a film", encoding="utf-8")
    with pytest.raises(DecodeError) as info:
        audio_channels(not_media)
    assert info.value.key == "error.decode.probe_failed"


def test_a_file_that_is_not_media_fails_the_audio_decode(tmp_path: Path) -> None:
    not_media = tmp_path / "notes.mp4"
    not_media.write_text("this is text, not a film", encoding="utf-8")
    with pytest.raises(DecodeError) as info:
        decode_window(not_media, 0.0, 1.0, PcmFormat(1, AUDIO_RATE))
    assert info.value.key == "error.decode.audio_failed"


def test_five_point_one_keeps_six_channels_in_their_order(tmp_path: Path) -> None:
    """A 5.1 track: the tone on the front-left channel only. Six channels come back, front left
    carries the tone, and the LFE channel (index 3) stays silent (DECISIONS #68)."""
    expr = f"{TONE}|0*t|0*t|0*t|0*t|0*t"
    out = tmp_path / "surround.mp4"
    subprocess.run(av_clip_argv(out, 4.0, expr, layout="5.1"), check=True)
    assert audio_channels(out) == 6
    window = decode_window(out, 1.5, 2.0, PcmFormat(6, AUDIO_RATE))
    assert window.shape[1] == 6
    assert float(np.max(np.abs(window[:, 0]))) > 0.1  # front left has the tone
    assert float(np.max(np.abs(window[:, 3]))) < 1e-4  # LFE is silent
