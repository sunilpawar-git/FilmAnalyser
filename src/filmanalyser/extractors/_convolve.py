"""FFT convolution in blocks (overlap-add), so memory depends on the block, not the signal.

A whole-window FFT of a 62 s, 48 kHz channel is an FFT of 4 million points (16 million for the 4x
oversampled true peak), and its workspace dominated the process's memory on 5.1 films (measured
2.2 GB peak, DECISIONS #99). Blocks of `BLOCK` samples give the same result to rounding error with a
workspace of a few megabytes.

This module's name starts with an underscore, so the registry never treats it as an extractor.
"""

from typing import Any

import numpy as np
import numpy.typing as npt

BLOCK = 1 << 16  # input samples per FFT block


def fft_convolve(
    signal: npt.NDArray[np.floating[Any]],
    kernel: npt.NDArray[np.float64],
    block: int = BLOCK,
) -> npt.NDArray[np.float64]:
    """The full linear convolution of 1-D `signal` with `kernel` (length len(signal)+len(kernel)-1),
    computed block by block."""
    taps = len(kernel)
    size = 1 << (block + taps - 1).bit_length()
    spectrum = np.fft.rfft(kernel, size)
    out = np.zeros(len(signal) + taps - 1)
    for start in range(0, len(signal), block):
        piece = np.fft.irfft(
            np.fft.rfft(signal[start : start + block].astype(np.float64), size) * spectrum, size
        )
        length = min(block, len(signal) - start) + taps - 1
        out[start : start + length] += piece[:length]
    return out
