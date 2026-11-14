"""The loudness and true-peak meter checked against EBU Tech 3341 (2023), Table 1, the EBU's own
minimum-requirement test signals. The expected values and tolerances are the table's; the signals
are synthesised here from its definitions (they are not the EBU's files).

The measures run at 48 kHz, the rate BS.1770 specifies, so this tests the algorithm itself. The
pipeline decodes at 16 kHz; that difference is measured separately (DECISIONS #61, #68)."""

import numpy as np
import numpy.typing as npt
import pytest

from filmanalyser.extractors._kweighting import k_weight
from filmanalyser.extractors._truepeak import true_peak_linear
from filmanalyser.extractors.loudness import integrated_lufs

RATE = 48000


def _sine(
    freq: float, dbfs: float, seconds: float, rate: int = RATE, phase_deg: float = 0.0
) -> npt.NDArray[np.float64]:
    """A sine whose peak is `dbfs` (dBFS), as in Table 1's per-channel peak levels."""
    t = np.arange(round(seconds * rate)) / rate
    amplitude = 10 ** (dbfs / 20)
    return np.asarray(
        amplitude * np.sin(2 * np.pi * freq * t + np.deg2rad(phase_deg)), dtype=np.float64
    )


def _stereo(mono: npt.NDArray[np.float64]) -> npt.NDArray[np.float32]:
    return np.stack([mono, mono], axis=1).astype(np.float32)


def _integrated(x: np.ndarray, rate: int = RATE) -> float:
    return integrated_lufs(k_weight(x, rate), 0, rate)


def _segments(*parts: npt.NDArray[np.float64]) -> npt.NDArray[np.float64]:
    return np.concatenate(parts)


# ---- Table 1, integrated loudness (cases 1 to 6) ------------------------------------


def test_case_1_stereo_sine_at_minus_23_dbfs_reads_minus_23_lufs() -> None:
    assert _integrated(_stereo(_sine(1000, -23.0, 20))) == pytest.approx(-23.0, abs=0.1)


def test_case_2_the_same_sine_at_minus_33_dbfs_reads_minus_33_lufs() -> None:
    assert _integrated(_stereo(_sine(1000, -33.0, 20))) == pytest.approx(-33.0, abs=0.1)


def test_case_3_quiet_then_loud_then_quiet_is_gated_to_the_loud_part() -> None:
    mono = _segments(_sine(1000, -36, 10), _sine(1000, -23, 60), _sine(1000, -36, 10))
    assert _integrated(_stereo(mono)) == pytest.approx(-23.0, abs=0.1)


def test_case_4_the_relative_gate_removes_very_quiet_and_quiet_passages() -> None:
    mono = _segments(
        _sine(1000, -72, 10), _sine(1000, -36, 10), _sine(1000, -23, 60),
        _sine(1000, -36, 10), _sine(1000, -72, 10),
    )  # fmt: skip
    assert _integrated(_stereo(mono)) == pytest.approx(-23.0, abs=0.1)


def test_case_5_a_loud_burst_inside_a_quieter_programme_is_measured_as_the_standard_says() -> None:
    mono = _segments(_sine(1000, -26, 20), _sine(1000, -20, 20.1), _sine(1000, -26, 20))
    assert _integrated(_stereo(mono)) == pytest.approx(-23.0, abs=0.1)


def test_case_6_five_point_one_channel_weights_are_the_standard_ones() -> None:
    """L and R at -28, centre at -24, surrounds at -30 dBFS; the surrounds weigh 1.41, so the mix
    reads -23 LUFS. A wrong surround weight would miss by about 1.5 dB."""
    n = round(20 * RATE)
    channels = np.zeros((n, 6), dtype=np.float32)
    channels[:, 0] = _sine(1000, -28, 20)
    channels[:, 1] = _sine(1000, -28, 20)
    channels[:, 2] = _sine(1000, -24, 20)
    channels[:, 4] = _sine(1000, -30, 20)
    channels[:, 5] = _sine(1000, -30, 20)
    assert _integrated(channels) == pytest.approx(-23.0, abs=0.1)


# ---- Table 1, true peak (cases 15 to 19) -------------------------------------------


def _true_peak(x: np.ndarray) -> float:
    return 20 * float(np.log10(true_peak_linear(x.astype(np.float64), 0)))


@pytest.mark.parametrize(
    ("case", "freq_div", "phase", "amplitude_fs", "expected"),
    [
        (15, 4, 0.0, 0.50, -6.0),
        (16, 4, 45.0, 0.50, -6.0),
        (17, 6, 60.0, 0.50, -6.0),
        (18, 8, 67.5, 0.50, -6.0),
        (19, 4, 45.0, 1.41, 3.0),
    ],
)
def test_true_peak_cases_15_to_19(
    case: int, freq_div: int, phase: float, amplitude_fs: float, expected: float
) -> None:
    """Table 1: a stereo sine at fs/N, with the stated amplitude (in full scale) and phase; the
    maximum true-peak level is the expected value, within +0.2 / -0.4 dB."""
    freq = RATE / freq_div
    t = np.arange(round(0.5 * RATE)) / RATE
    tone = amplitude_fs * np.sin(2 * np.pi * freq * t + np.deg2rad(phase))
    fade = round(0.010 * RATE)  # Table 1: the tone is tapered with a 10 ms fade in and out
    ramp = 0.5 - 0.5 * np.cos(np.pi * np.arange(fade) / fade)
    tone[:fade] *= ramp
    tone[-fade:] *= ramp[::-1]
    level = _true_peak(_stereo(tone))
    assert expected - 0.4 <= level <= expected + 0.2, f"case {case}: {level:.2f} dBTP"


def test_a_sudden_end_to_the_window_does_not_create_an_overshoot() -> None:
    """Zero padding past the window's end must not ring into a false peak (DECISIONS #71): a
    sine with a fade-in and an abrupt end reads its true level, not 0.7 dB above it."""
    t = np.arange(round(0.5 * RATE)) / RATE
    tone = 0.5 * np.sin(2 * np.pi * (RATE / 8) * t + np.deg2rad(67.5))
    fade = round(0.010 * RATE)
    tone[:fade] *= 0.5 - 0.5 * np.cos(np.pi * np.arange(fade) / fade)  # fade in only
    assert _true_peak(_stereo(tone)) <= -6.0 + 0.1


def test_the_ten_millisecond_taper_of_table_1_gives_the_expected_level() -> None:
    """With the taper that Table 1 specifies, the same tone reads the expected level exactly."""
    t = np.arange(round(0.5 * RATE)) / RATE
    tone = 0.5 * np.sin(2 * np.pi * (RATE / 8) * t + np.deg2rad(67.5))
    fade = round(0.010 * RATE)
    ramp = 0.5 - 0.5 * np.cos(np.pi * np.arange(fade) / fade)
    tone[:fade] *= ramp
    tone[-fade:] *= ramp[::-1]
    assert _true_peak(_stereo(tone)) == pytest.approx(-6.0, abs=0.05)
