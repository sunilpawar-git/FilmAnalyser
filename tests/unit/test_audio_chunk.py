"""Audio on a Chunk: the same window as its frames (overlap included), read-only, pure (no I/O)."""

import dataclasses

import numpy as np
import pytest

from filmanalyser.core.chunk import Audio, Chunk
from filmanalyser.core.config import AUDIO_RATE, VOICE_WINDOW
from filmanalyser.core.errors import InputError


def _frames(count: int) -> np.ndarray:
    return np.zeros((count, 2, 2, 3), dtype=np.uint8)


def _audio(seconds: float, start_s: float, channels: int = 1) -> Audio:
    samples = np.zeros((round(seconds * AUDIO_RATE), channels), dtype=np.float32)
    return Audio(rate=AUDIO_RATE, start_s=start_s, samples=samples)


def _chunk(audio: Audio | None, context: int = 4) -> Chunk:
    # 2 fps, 10 frames, 4 context frames: the window starts 2 s before the core (start_s = 10 s)
    return Chunk(
        index=1, start_s=10.0, end_s=15.0, fps=2.0, frames=_frames(14), context_frames=context,
        audio=audio,
    )  # fmt: skip


def test_chunk_without_audio_is_the_default() -> None:
    assert _chunk(None).audio is None


def test_core_audio_starts_where_the_core_frames_start() -> None:
    chunk = _chunk(_audio(7.0, start_s=8.0))  # window 8 s..15 s, core from 10 s
    core = chunk.core_audio
    assert len(core) == round(5.0 * AUDIO_RATE)
    assert chunk.audio_core_offset == round(2.0 * AUDIO_RATE)


def test_audio_offset_is_zero_for_a_chunk_without_context() -> None:
    chunk = Chunk(
        index=0, start_s=0.0, end_s=1.0, fps=2.0, frames=_frames(2), context_frames=0,
        audio=_audio(1.0, start_s=0.0),
    )  # fmt: skip
    assert chunk.audio_core_offset == 0
    assert len(chunk.core_audio) == AUDIO_RATE


def test_audio_must_start_where_the_frames_start() -> None:
    with pytest.raises(InputError) as info:
        _chunk(_audio(5.0, start_s=9.0))  # frames start at 8 s, audio at 9 s
    assert info.value.fields == {"name": "audio"}


def test_audio_samples_are_read_only_and_the_callers_array_is_not_frozen() -> None:
    source = np.zeros((AUDIO_RATE, 1), dtype=np.float32)
    audio = Audio(rate=AUDIO_RATE, start_s=0.0, samples=source)
    source[0, 0] = 0.5  # the caller's array stays writable
    with pytest.raises(ValueError, match="read-only"):
        audio.samples[0, 0] = 0.1


@pytest.mark.parametrize(
    ("rate", "shape", "dtype"),
    [
        (0, (10, 1), np.float32),  # rate must be positive
        (AUDIO_RATE, (10,), np.float32),  # samples must be 2-D (frames, channels)
        (AUDIO_RATE, (10, 3), np.float32),  # mono or stereo only
        (AUDIO_RATE, (10, 1), np.float64),  # float32 is the one decoder format
        (AUDIO_RATE, (0, 1), np.float32),  # at least one sample
    ],
)
def test_bad_audio_is_refused(rate: int, shape: tuple[int, ...], dtype: type) -> None:
    with pytest.raises(InputError):
        Audio(rate=rate, start_s=0.0, samples=np.zeros(shape, dtype=dtype))


def test_non_finite_samples_are_refused() -> None:
    samples = np.zeros((10, 1), dtype=np.float32)
    samples[3, 0] = np.nan
    with pytest.raises(InputError):
        Audio(rate=AUDIO_RATE, start_s=0.0, samples=samples)


def test_voice_probabilities_are_one_per_window() -> None:
    samples = np.zeros((3 * VOICE_WINDOW, 1), dtype=np.float32)
    voice = np.array([0.0, 0.5, 1.0], dtype=np.float32)
    audio = Audio(rate=AUDIO_RATE, start_s=0.0, samples=samples, voice=voice)
    assert audio.voice is not None and audio.voice.shape == (3,)


def test_voice_must_be_one_dimensional_and_finite() -> None:
    samples = np.zeros((VOICE_WINDOW, 1), dtype=np.float32)
    with pytest.raises(InputError):
        Audio(rate=AUDIO_RATE, start_s=0.0, samples=samples, voice=np.zeros((1, 1), np.float32))
    with pytest.raises(InputError):
        Audio(
            rate=AUDIO_RATE, start_s=0.0, samples=samples,
            voice=np.array([np.inf], dtype=np.float32),
        )  # fmt: skip


def test_audio_is_immutable() -> None:
    audio = _audio(1.0, start_s=0.0)
    with pytest.raises(dataclasses.FrozenInstanceError):
        audio.rate = 8000  # type: ignore[misc]


def test_offset_and_core_audio_need_audio() -> None:
    chunk = _chunk(None)
    with pytest.raises(InputError):
        _ = chunk.audio_core_offset
    with pytest.raises(InputError):
        _ = chunk.core_audio
