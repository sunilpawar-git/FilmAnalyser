import dataclasses

import pytest

from filmanalyser.core.config import Config
from filmanalyser.core.errors import InputError


def test_defaults_come_from_the_product_contract() -> None:
    config = Config()
    assert config.chunk_seconds == 60.0  # README: 60 s chunks
    assert config.ram_budget_mb == 2048  # ACCEPTANCE: peak RAM < 2 GB
    assert config.overlap_seconds == 2.0
    assert config.analysis_fps == 12.0
    assert config.frame_width == 160


def test_derived_frame_counts() -> None:
    config = Config()
    assert config.frames_per_chunk == 720
    assert config.overlap_frames == 24
    assert Config(overlap_seconds=0.0).overlap_frames == 0


def test_config_is_immutable() -> None:
    with pytest.raises(dataclasses.FrozenInstanceError):
        Config().chunk_seconds = 1.0  # type: ignore[misc]


@pytest.mark.parametrize("field", ["chunk_seconds", "ram_budget_mb", "analysis_fps", "frame_width"])
@pytest.mark.parametrize("value", [0, -1])
def test_non_positive_values_rejected(field: str, value: float) -> None:
    with pytest.raises(InputError, match=field):
        Config(**{field: value})  # type: ignore[arg-type]


def test_replace_revalidates() -> None:
    with pytest.raises(InputError):
        dataclasses.replace(Config(), chunk_seconds=0.0)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"overlap_seconds": -1.0},
        {"overlap_seconds": 60.0},  # must be shorter than the chunk
        {"chunk_seconds": 0.05, "analysis_fps": 10.0, "overlap_seconds": 0.0},  # < 1 frame
        {"frame_width": 3},  # must be even (video scaling)
    ],
)
def test_inconsistent_geometry_rejected(kwargs: dict[str, float]) -> None:
    with pytest.raises(InputError):
        Config(**kwargs)  # type: ignore[arg-type]
