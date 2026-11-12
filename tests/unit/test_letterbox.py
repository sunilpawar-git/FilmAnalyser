"""Letterbox bars: known bar heights are found exactly; a picture with no bars reports none."""

import numpy as np

from filmanalyser.core.chunk import Frames
from filmanalyser.extractors.letterbox import letterbox_bars

HEIGHT, WIDTH = 90, 16


def framed(top: int, bottom: int, *, picture: int = 200, frames: int = 6) -> Frames:
    image = np.full((frames, HEIGHT, WIDTH, 3), picture, dtype=np.uint8)
    image[:, :top] = 0
    if bottom:
        image[:, HEIGHT - bottom :] = 0
    return image


def test_known_bars_are_measured_exactly() -> None:
    assert letterbox_bars(framed(top=12, bottom=12)) == (12, 12)


def test_bars_of_unequal_height_are_measured_per_side() -> None:
    assert letterbox_bars(framed(top=7, bottom=3)) == (7, 3)


def test_a_full_frame_picture_has_no_bars() -> None:
    assert letterbox_bars(framed(top=0, bottom=0)) == (0, 0)


def test_a_single_dark_frame_in_the_chunk_does_not_create_bars() -> None:
    frames = framed(top=0, bottom=0, frames=9)
    frames[4, :10] = 0  # one black flash: the median over the chunk ignores it
    assert letterbox_bars(frames) == (0, 0)


def test_an_entirely_black_chunk_is_not_a_letterbox() -> None:
    assert letterbox_bars(np.zeros((3, HEIGHT, WIDTH, 3), dtype=np.uint8)) == (0, 0)
