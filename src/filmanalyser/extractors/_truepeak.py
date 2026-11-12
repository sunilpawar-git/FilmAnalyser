"""True peak (BS.1770-4 Annex 2 in spirit, DECISIONS #68): the largest absolute value the waveform
reaches between its samples. The signal is oversampled by UPSAMPLE with a windowed-sinc
interpolator, then the largest value of the oversampled signal is taken.

Pure numpy, no I/O. The interpolator is a Hann-windowed sinc of HALF_TAPS original samples on each
side; zeros outside the window count as silence, so a window's edges add no false peaks.

This module's name starts with an underscore, so the registry never treats it as an extractor.
"""

import numpy as np
import numpy.typing as npt

UPSAMPLE = 4
HALF_TAPS = 8  # original samples either side of the interpolated point


def _kernel() -> npt.NDArray[np.float64]:
    offsets = np.arange(-HALF_TAPS * UPSAMPLE, HALF_TAPS * UPSAMPLE + 1) / UPSAMPLE
    window = 0.5 + 0.5 * np.cos(np.pi * offsets / (HALF_TAPS + 1))
    window[np.abs(offsets) > HALF_TAPS + 1] = 0.0
    return np.asarray(np.sinc(offsets) * window, dtype=np.float64)


_KERNEL = _kernel()


def oversample(channel: npt.NDArray[np.float64]) -> npt.NDArray[np.float64]:
    """`channel` (1-D) at UPSAMPLE times its rate: the original samples land on every UPSAMPLE-th
    point and the interpolator fills the rest."""
    stuffed = np.zeros(len(channel) * UPSAMPLE)
    stuffed[::UPSAMPLE] = channel
    size = 1 << (len(stuffed) + len(_KERNEL) - 1).bit_length()
    spectrum = np.fft.rfft(_KERNEL, size) * np.fft.rfft(stuffed, size)
    full = np.fft.irfft(spectrum, size)
    offset = HALF_TAPS * UPSAMPLE  # the kernel's centre sits at its middle tap
    return np.asarray(full[offset : offset + len(stuffed)], dtype=np.float64)


def true_peak_linear(samples: npt.NDArray[np.float64], core_offset: int) -> float:
    """The largest |value| between samples over the core (`core_offset` samples into the window),
    for a (count, channels) window. Zero for an empty core."""
    peak = 0.0
    for channel in range(samples.shape[1]):
        upsampled = oversample(samples[:, channel])
        core = upsampled[core_offset * UPSAMPLE :]
        if core.size:
            peak = max(peak, float(np.max(np.abs(core))))
    return peak
