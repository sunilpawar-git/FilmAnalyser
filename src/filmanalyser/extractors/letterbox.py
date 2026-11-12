"""Letterbox bars: the black rows above and below the picture (DECISIONS #13).

A row is a bar when its brightness, taken as the median over the chunk's frames, is below
LETTERBOX_LUMA. The median keeps a single dark flash from creating bars. A chunk that is dark
everywhere has no picture to crop, so it reports no bars. This module is a helper: it defines no
EXTRACTOR and is not registered (DECISIONS #50).
"""

import numpy as np
import numpy.typing as npt

from filmanalyser.core.chunk import Frames
from filmanalyser.core.config import LETTERBOX_LUMA, LUMA_WEIGHTS


def _row_brightness(frames: Frames) -> npt.NDArray[np.float64]:
    """Median over frames of each row's mean brightness (0..1), shape (height,)."""
    weights = np.asarray(LUMA_WEIGHTS, dtype=np.float64)
    means = np.empty((len(frames), frames.shape[1]))
    for index, frame in enumerate(frames):
        luma = frame.astype(np.float64) @ weights / 255.0  # (height, width)
        means[index] = luma.mean(axis=1)
    return np.median(means, axis=0)


def letterbox_bars(frames: Frames) -> tuple[int, int]:
    """(rows of bar above, rows of bar below) for a chunk of frames (height, width, 3)."""
    dark = _row_brightness(frames) < LETTERBOX_LUMA
    if dark.all():
        return (0, 0)
    top = int(np.argmax(~dark))
    bottom = int(np.argmax(~dark[::-1]))
    return (top, bottom)
