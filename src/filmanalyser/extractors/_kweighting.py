"""ITU-R BS.1770 K-weighting for any sample rate (pure, numpy only; DECISIONS #61).

The standard gives the filter as two analogue prototypes: a high shelf (the "pre-filter") and an RLB
high-pass. Both are turned into digital biquads by the bilinear transform at the rate in use. The
48 kHz result reproduces the coefficients published in BS.1770-4 (tested). The filter is applied as
its impulse response (an FFT convolution), which is exact for a filter whose response has decayed
long before the end of the truncated response.

This module's name starts with an underscore, so the registry never treats it as an extractor.
"""

import math
from dataclasses import dataclass
from functools import cache

import numpy as np
import numpy.typing as npt

from filmanalyser.core.chunk import Samples

# BS.1770-4 analogue prototype parameters (frequency Hz, gain dB, Q).
_SHELF_F0, _SHELF_GAIN_DB, _SHELF_Q = 1681.974450955533, 3.999843853973347, 0.7071752369554196
_SHELF_EXPONENT = 0.4996667741545416  # the shelf's Vb = Vh ** exponent
_HIGHPASS_F0, _HIGHPASS_Q = 38.13547087602444, 0.5003270373238773
_RESPONSE_TAPS = 8192  # 0.5 s at 16 kHz: the 38 Hz high-pass has decayed to nothing well before


@dataclass(frozen=True)
class Biquad:
    """One second-order section, normalised so the denominator starts with 1."""

    b: tuple[float, float, float]
    a: tuple[float, float]  # a1, a2 (a0 is 1)


def pre_filter(rate: float) -> Biquad:
    """Stage 1: the high shelf that models the head's acoustic effect."""
    k = math.tan(math.pi * _SHELF_F0 / rate)
    vh = 10 ** (_SHELF_GAIN_DB / 20)
    vb = vh**_SHELF_EXPONENT
    a0 = 1 + k / _SHELF_Q + k * k
    b = (
        (vh + vb * k / _SHELF_Q + k * k) / a0,
        2 * (k * k - vh) / a0,
        (vh - vb * k / _SHELF_Q + k * k) / a0,
    )
    a = (2 * (k * k - 1) / a0, (1 - k / _SHELF_Q + k * k) / a0)
    return Biquad(b, a)  # fmt: skip


def rlb_filter(rate: float) -> Biquad:
    """Stage 2: the RLB weighting, a high-pass that removes content below about 38 Hz."""
    k = math.tan(math.pi * _HIGHPASS_F0 / rate)
    a0 = 1 + k / _HIGHPASS_Q + k * k
    a = (2 * (k * k - 1) / a0, (1 - k / _HIGHPASS_Q + k * k) / a0)
    return Biquad((1.0, -2.0, 1.0), a)


@cache
def biquads(rate: int) -> tuple[Biquad, Biquad]:
    """The two cascaded stages for `rate` Hz, in the order the standard applies them."""
    return pre_filter(rate), rlb_filter(rate)


def _impulse_response(rate: int) -> npt.NDArray[np.float64]:
    """The cascade's response to a unit impulse, `_RESPONSE_TAPS` long (direct form I)."""
    response = np.zeros(_RESPONSE_TAPS)
    response[0] = 1.0
    for stage in biquads(rate):
        response = _run(stage, response)
    return response


def _run(stage: Biquad, x: npt.NDArray[np.float64]) -> npt.NDArray[np.float64]:
    b0, b1, b2 = stage.b
    a1, a2 = stage.a
    y = np.zeros_like(x)
    x1 = x2 = y1 = y2 = 0.0
    for n, xn in enumerate(x.tolist()):
        yn = b0 * xn + b1 * x1 + b2 * x2 - a1 * y1 - a2 * y2
        y[n] = yn
        x2, x1, y2, y1 = x1, xn, y1, yn
    return y


@cache
def _kernel(rate: int) -> npt.NDArray[np.float64]:
    return _impulse_response(rate)


def k_weight(samples: Samples, rate: int) -> npt.NDArray[np.float64]:
    """K-weight each channel of `samples` (count, channels). Output has the same shape."""
    kernel = _kernel(rate)
    count = len(samples)
    size = 1 << (count + len(kernel) - 1).bit_length()
    spectrum = np.fft.rfft(kernel, size)[:, None]
    signal = np.fft.rfft(samples.astype(np.float64), size, axis=0)
    return np.asarray(np.fft.irfft(signal * spectrum, size, axis=0)[:count], dtype=np.float64)
