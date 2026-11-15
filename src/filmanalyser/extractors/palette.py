"""Dominant colours of a picture: a coarse, deterministic palette (DECISIONS 106).

Every pixel falls into one of LEVELS ** 3 cubes of RGB space (LEVELS cubes per channel). The
PALETTE_SIZE most common cubes are the palette, each reported as its centre colour (0..1 per
channel) and the share of the picture's pixels it holds. Equal shares are ordered by cube index, so
the result never depends on chance. A cube nobody uses is reported as zeros with a share of 0. This
module is a helper: it defines no EXTRACTOR and is not registered.
"""

import numpy as np
import numpy.typing as npt

from filmanalyser.core.chunk import Frames
from filmanalyser.core.features import PALETTE_PARTS, PALETTE_SIZE

LEVELS = 4  # per channel; a power of two
_SHIFT = 8 - LEVELS.bit_length() + 1  # 8-bit value -> its level (6 for 4 levels)
_CUBES = LEVELS**3
FEATURES = tuple(
    f"palette_{rank}_{part}" for rank in range(1, PALETTE_SIZE + 1) for part in PALETTE_PARTS
)


def cube_counts(frames: Frames, top: int, bottom: int) -> npt.NDArray[np.int64]:
    """Pixels per cube over the rows of each frame that are picture (not bars)."""
    counts = np.zeros(_CUBES, dtype=np.int64)
    for frame in frames:
        level = frame[top : frame.shape[0] - bottom] >> _SHIFT
        cube = (level[..., 0].astype(np.intp) * LEVELS + level[..., 1]) * LEVELS + level[..., 2]
        counts += np.bincount(cube.ravel(), minlength=_CUBES)
    return counts


def _centre(cube: int) -> tuple[float, float, float]:
    """The middle of a cube as (red, green, blue) in 0..1."""
    size = 256 // LEVELS
    blue, rest = cube % LEVELS, cube // LEVELS
    red, green = rest // LEVELS, rest % LEVELS

    def middle(level: int) -> float:
        return (level * size + size // 2) / 255.0

    return (middle(red), middle(green), middle(blue))


def palette_features(counts: npt.NDArray[np.int64]) -> dict[str, float]:
    total = int(counts.sum())
    order = np.argsort(-counts, kind="stable")[:PALETTE_SIZE]  # stable: ties go to the lower cube
    out: dict[str, float] = {}
    for rank, cube in enumerate(order, 1):
        held = int(counts[cube])
        colour = _centre(int(cube)) if held else (0.0, 0.0, 0.0)
        values = (*colour, held / total if total else 0.0)
        out.update(
            {f"palette_{rank}_{part}": v for part, v in zip(PALETTE_PARTS, values, strict=True)}
        )
    return out
