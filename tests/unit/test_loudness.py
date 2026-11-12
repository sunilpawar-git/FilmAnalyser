"""Loudness (ITU-R BS.1770 K-weighting, gated) checked against reference values (pure, no I/O).

Reference values come from the standard's own arithmetic: loudness = -0.691 + 10 log10(mean square
of the K-weighted channels summed), with K-weighting unity at 1 kHz. The K-filter coefficients are
checked against the published 48 kHz values of BS.1770-4.
"""

import numpy as np
import pytest

from filmanalyser.core.chunk import Audio, Chunk
from filmanalyser.core.config import AUDIO_RATE, LOUDNESS_ABS_GATE_LUFS, PEAK_FLOOR_DBFS
from filmanalyser.core.errors import InputError
from filmanalyser.core.extractor import Extractor
from filmanalyser.extractors._kweighting import Biquad, biquads, k_weight, pre_filter, rlb_filter
from filmanalyser.extractors.loudness import EXTRACTOR, integrated_lufs, peak_dbfs

RATE = AUDIO_RATE
TOLERANCE_LU = 0.1


def _sine(seconds: float, amplitude: float, freq: float = 1000.0, channels: int = 1) -> np.ndarray:
    t = np.arange(round(seconds * RATE)) / RATE
    mono = amplitude * np.sin(2 * np.pi * freq * t)
    return np.repeat(mono[:, None], channels, axis=1).astype(np.float32)


def _expected(amplitude: float, channels: int = 1) -> float:
    """BS.1770 loudness of a steady sine: the standard's arithmetic at 48 kHz, where the K-weighting
    gain at 1 kHz is K_1KHZ_DB (the -0.691 offset is the standard's own; a full-scale mono
    sine reads about -3.01 LUFS)."""
    return float(-0.691 + K_1KHZ_DB + 10 * np.log10(channels * amplitude**2 / 2))


def _lufs(samples: np.ndarray, core_offset: int = 0) -> float:
    return integrated_lufs(k_weight(samples, RATE), core_offset, RATE)


def _gain_db(filt: Biquad, freq: float, rate: int) -> float:
    """Magnitude response of a biquad at `freq`, in dB."""
    b, a = filt.b, filt.a
    z = np.exp(1j * 2 * np.pi * freq / rate)
    h = (b[0] + b[1] / z + b[2] / z**2) / (1 + a[0] / z + a[1] / z**2)
    return float(20 * np.log10(abs(h)))


K_1KHZ_DB = sum(_gain_db(stage, 1000.0, 48000) for stage in biquads(48000))  # the standard's gain


# ---- K-weighting filter --------------------------------------------------------------------------


def test_k_weighting_matches_the_published_48khz_coefficients() -> None:
    # BS.1770-4 Annex 1, Table 1 (48 kHz): the reference the derivation must reproduce.
    shelf = pre_filter(48000)
    assert shelf.b == pytest.approx(
        (1.53512485958697, -2.69169618940638, 1.19839281085285), abs=1e-9
    )
    assert shelf.a == pytest.approx((-1.69065929318241, 0.73248077421585), abs=1e-9)
    highpass = rlb_filter(48000)
    assert highpass.b == pytest.approx((1.0, -2.0, 1.0), abs=1e-12)
    assert highpass.a == pytest.approx((-1.99004745483398, 0.99007225036621), abs=1e-9)


def test_k_weighting_gain_at_one_kilohertz_is_the_published_value() -> None:
    assert pytest.approx(0.698, abs=0.01) == K_1KHZ_DB  # BS.1770: the -0.691 offset absorbs it


def test_16khz_response_tracks_the_48khz_reference_below_4khz() -> None:
    # Measured error: at most 0.15 dB from 40 Hz to 4 kHz. Above that the 16 kHz design drifts.
    for freq in (40.0, 100.0, 500.0, 1000.0, 2000.0, 4000.0):
        reference = sum(_gain_db(stage, freq, 48000) for stage in biquads(48000))
        here = sum(_gain_db(stage, freq, RATE) for stage in biquads(RATE))
        assert here == pytest.approx(reference, abs=0.2), freq


def test_k_weighting_boosts_the_highs_and_removes_the_lows() -> None:
    assert _gain_db(pre_filter(RATE), 4000.0, RATE) > 2.0  # high shelf: about +4 dB at the top
    assert _gain_db(rlb_filter(RATE), 20.0, RATE) < -10.0  # RLB high-pass: deep cut below 38 Hz


def test_k_weight_keeps_shape_and_is_float64() -> None:
    weighted = k_weight(_sine(0.5, 0.5, channels=2), RATE)
    assert weighted.shape == (round(0.5 * RATE), 2)
    assert weighted.dtype == np.float64


# ---- integrated loudness against reference values ------------------------------------------------


def test_steady_mono_sine_matches_the_formula() -> None:
    assert _lufs(_sine(10.0, 0.5)) == pytest.approx(_expected(0.5), abs=TOLERANCE_LU)


def test_identical_stereo_channels_add_three_db() -> None:
    stereo = _sine(10.0, 0.5, channels=2)
    assert _lufs(stereo) == pytest.approx(_expected(0.5, channels=2), abs=TOLERANCE_LU)
    assert _lufs(stereo) - _lufs(_sine(10.0, 0.5)) == pytest.approx(3.01, abs=TOLERANCE_LU)


def test_halving_the_amplitude_lowers_loudness_by_six_db() -> None:
    loud, quiet = _lufs(_sine(10.0, 0.5)), _lufs(_sine(10.0, 0.25))
    assert loud - quiet == pytest.approx(6.02, abs=TOLERANCE_LU)


def test_digital_silence_reads_the_absolute_gate_floor() -> None:
    assert _lufs(np.zeros((round(5 * RATE), 1), dtype=np.float32)) == LOUDNESS_ABS_GATE_LUFS


def test_a_very_quiet_passage_is_removed_by_the_absolute_gate() -> None:
    loud = _sine(10.0, 0.5)
    whisper = _sine(10.0, 0.0002)  # about -77 LUFS: below the -70 LUFS absolute gate
    mixed = np.concatenate([loud, whisper])
    assert _lufs(mixed) == pytest.approx(_expected(0.5), abs=TOLERANCE_LU)


def test_a_passage_far_below_the_loud_part_is_removed_by_the_relative_gate() -> None:
    loud = _sine(10.0, 0.5)
    quiet = _sine(10.0, 0.05)  # 20 dB down: more than 10 LU below the mean, so it is gated out
    mixed = np.concatenate([loud, quiet])
    assert _lufs(mixed) == pytest.approx(_expected(0.5), abs=TOLERANCE_LU)


def test_a_passage_within_the_relative_gate_still_counts() -> None:
    loud = _sine(10.0, 0.5)
    slightly_quieter = _sine(10.0, 0.5 * 10 ** (-4 / 20))  # 4 dB down: inside the 10 LU gate
    both = _lufs(np.concatenate([loud, slightly_quieter]))
    assert _expected(0.5) - TOLERANCE_LU > both > _expected(0.5) - 4.0


def test_a_clip_shorter_than_one_gating_block_is_measured_as_one_block() -> None:
    assert _lufs(_sine(0.2, 0.5)) == pytest.approx(_expected(0.5), abs=TOLERANCE_LU)


def test_only_the_core_window_is_measured_after_context() -> None:
    context = _sine(2.0, 0.0)  # two seconds of overlap at silence
    core = _sine(5.0, 0.5)
    window = np.concatenate([context, core])
    assert _lufs(window, core_offset=len(context)) == pytest.approx(
        _expected(0.5), abs=TOLERANCE_LU
    )


def test_an_empty_core_reads_the_floor() -> None:
    assert integrated_lufs(np.zeros((10, 1)), core_offset=10, rate=RATE) == LOUDNESS_ABS_GATE_LUFS


# ---- sample peak ---------------------------------------------------------------------------------


def test_peak_of_a_half_scale_sine_is_minus_six_dbfs() -> None:
    assert peak_dbfs(_sine(1.0, 0.5)) == pytest.approx(-6.02, abs=0.01)


def test_peak_of_silence_is_the_floor() -> None:
    assert peak_dbfs(np.zeros((100, 1), dtype=np.float32)) == PEAK_FLOOR_DBFS


# ---- the extractor -------------------------------------------------------------------------------


def _chunk(samples: np.ndarray, context_s: float = 0.0) -> Chunk:
    context = round(context_s * 2.0)  # 2 fps: one frame per half second
    core_s = len(samples) / RATE - context_s
    frames = np.zeros((context + round(core_s * 2.0), 2, 2, 3), dtype=np.uint8)
    audio = Audio(rate=RATE, start_s=0.0, samples=samples)
    return Chunk(
        index=0, start_s=context_s, end_s=context_s + core_s, fps=2.0, frames=frames,
        context_frames=context, audio=audio,
    )  # fmt: skip


def test_the_extractor_is_registered_as_needing_audio() -> None:
    assert isinstance(EXTRACTOR, Extractor)
    assert EXTRACTOR.name == "loudness"
    assert EXTRACTOR.features == ("integrated_lufs", "peak_dbfs")
    assert EXTRACTOR.needs_audio is True


def test_extract_returns_both_features_for_the_core_window() -> None:
    chunk = _chunk(_sine(4.0, 0.5), context_s=0.0)
    out = EXTRACTOR.extract(chunk)
    assert set(out) == {"integrated_lufs", "peak_dbfs"}
    assert out["integrated_lufs"] == pytest.approx(_expected(0.5), abs=TOLERANCE_LU)
    assert out["peak_dbfs"] == pytest.approx(-6.02, abs=0.01)


def test_extract_refuses_a_chunk_without_audio() -> None:
    frames = np.zeros((2, 2, 2, 3), dtype=np.uint8)
    chunk = Chunk(index=0, start_s=0.0, end_s=1.0, fps=2.0, frames=frames, context_frames=0)
    with pytest.raises(InputError, match="audio"):
        EXTRACTOR.extract(chunk)
