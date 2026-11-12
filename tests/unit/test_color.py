"""Colour and light features checked against frames whose colour is known exactly."""

from typing import Any

import numpy as np
import pytest

from filmanalyser.core.chunk import Chunk
from filmanalyser.core.config import LUMA_WEIGHTS
from filmanalyser.extractors.color import EXTRACTOR, Color

FPS = 10.0


def chunk_of(frames: np.ndarray[Any, Any], context: int = 0) -> Chunk:
    return Chunk(0, 0.0, len(frames) / FPS, FPS, frames.astype(np.uint8), context_frames=context)


def solid(colour: tuple[int, int, int], height: int = 8, width: int = 8) -> np.ndarray[Any, Any]:
    return np.broadcast_to(np.array(colour, dtype=np.uint8), (4, height, width, 3)).copy()


def test_white_is_full_brightness_and_colourless() -> None:
    features = Color().extract(chunk_of(solid((255, 255, 255))))
    assert features["brightness"] == pytest.approx(1.0)
    assert features["colourfulness"] == 0.0
    assert features["warmth"] == 0.0
    assert features["contrast"] == 0.0


def test_pure_red_has_the_bt709_red_luma_and_full_warmth() -> None:
    features = Color().extract(chunk_of(solid((255, 0, 0))))
    assert features["brightness"] == pytest.approx(LUMA_WEIGHTS[0])
    assert features["colourfulness"] == pytest.approx(1.0)
    assert features["warmth"] == pytest.approx(1.0)


def test_pure_blue_is_cool() -> None:
    features = Color().extract(chunk_of(solid((0, 0, 255))))
    assert features["brightness"] == pytest.approx(LUMA_WEIGHTS[2])
    assert features["warmth"] == pytest.approx(-1.0)


def test_mid_grey_is_its_own_brightness() -> None:
    assert Color().extract(chunk_of(solid((128, 128, 128))))["brightness"] == pytest.approx(
        128 / 255
    )


def test_half_black_half_white_has_a_contrast_of_one_half() -> None:
    frames = np.zeros((2, 8, 8, 3), dtype=np.uint8)
    frames[:, :, 4:] = 255
    assert Color().extract(chunk_of(frames))["contrast"] == pytest.approx(0.5)


def test_letterbox_bars_are_excluded_from_the_colour_statistics() -> None:
    frames = solid((255, 255, 255), height=20)
    frames[:, :5] = 0
    frames[:, 15:] = 0  # 10 rows of bars; the picture is white
    features = Color().extract(chunk_of(frames))
    assert features["letterbox"] == pytest.approx(0.5)
    assert features["brightness"] == pytest.approx(1.0)


def test_only_core_frames_are_measured() -> None:
    frames = np.concatenate([solid((0, 0, 0)), solid((255, 255, 255))])
    features = Color().extract(chunk_of(frames, context=4))
    assert features["brightness"] == pytest.approx(1.0)


def test_all_features_are_finite_on_an_all_black_chunk() -> None:
    features = Color().extract(chunk_of(np.zeros((3, 8, 8, 3), dtype=np.uint8)))
    assert all(np.isfinite(v) for v in features.values())
    assert features["brightness"] == 0.0


def test_declared_features_match_the_output_exactly() -> None:
    assert EXTRACTOR.name == "color"
    features = EXTRACTOR.features
    assert set(Color().extract(chunk_of(solid((1, 2, 3))))) == set(features)
