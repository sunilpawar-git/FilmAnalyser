"""Colour and light per chunk, measured over the picture only (letterbox bars excluded).

Brightness is the mean BT.709 luma (0..1). Contrast is the spread of luma. Colourfulness is the
mean of (max - min) over the channels (0..1). Warmth is the mean of (R - B) (-1..1). Letterbox is
the share of the frame height that is bars (0..1). Every value is finite; an empty picture is
reported as zero rather than NaN (DECISIONS #43).
"""

from collections.abc import Mapping
from dataclasses import dataclass

import numpy as np

from filmanalyser.core.chunk import Chunk
from filmanalyser.core.config import LUMA_WEIGHTS
from filmanalyser.extractors.letterbox import letterbox_bars

NAME = "color"
VERSION = 1
FEATURES = ("brightness", "contrast", "colourfulness", "warmth", "letterbox")


def _sums(picture: np.ndarray) -> tuple[float, float, float, float, float]:
    """(count, sum of luma, sum of luma squared, sum of colourfulness, sum of warmth)."""
    rgb = picture.astype(np.float64) / 255.0
    luma = rgb @ np.asarray(LUMA_WEIGHTS, dtype=np.float64)
    chroma = rgb.max(axis=2) - rgb.min(axis=2)
    warm = rgb[..., 0] - rgb[..., 2]
    return (
        float(luma.size),
        float(luma.sum()),
        float((luma * luma).sum()),
        float(chroma.sum()),
        float(warm.sum()),
    )


def picture_features(chunk: Chunk) -> dict[str, float]:
    frames = chunk.core
    top, bottom = letterbox_bars(frames)
    height = frames.shape[1]
    total = [0.0, 0.0, 0.0, 0.0, 0.0]
    for frame in frames:
        for slot, value in enumerate(_sums(frame[top : height - bottom])):
            total[slot] += value
    count = total[0] or 1.0  # nothing left after cropping: zeros, never NaN (DECISIONS #43)
    mean = total[1] / count
    spread = max(total[2] / count - mean * mean, 0.0)
    return {
        "brightness": mean,
        "contrast": float(np.sqrt(spread)),
        "colourfulness": total[3] / count,
        "warmth": total[4] / count,
        "letterbox": (top + bottom) / height,
    }


@dataclass(frozen=True)
class Color:
    name: str = NAME
    version: int = VERSION
    features: tuple[str, ...] = FEATURES
    needs_audio: bool = False

    def extract(self, chunk: Chunk) -> Mapping[str, float]:
        return picture_features(chunk)


EXTRACTOR = Color()
