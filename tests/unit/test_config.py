import dataclasses

import pytest

from filmanalyser.core.config import Config
from filmanalyser.core.errors import InputError


def test_defaults_come_from_the_product_contract() -> None:
    config = Config()
    assert config.chunk_seconds == 60.0  # README: 60 s chunks
    assert config.ram_budget_mb == 2048  # ACCEPTANCE: peak RAM < 2 GB


def test_config_is_immutable() -> None:
    with pytest.raises(dataclasses.FrozenInstanceError):
        Config().chunk_seconds = 1.0  # type: ignore[misc]


@pytest.mark.parametrize("field", ["chunk_seconds", "ram_budget_mb"])
@pytest.mark.parametrize("value", [0, -1])
def test_non_positive_values_rejected(field: str, value: float) -> None:
    with pytest.raises(InputError, match=field):
        Config(**{field: value})  # type: ignore[arg-type]


def test_replace_revalidates() -> None:
    with pytest.raises(InputError):
        dataclasses.replace(Config(), chunk_seconds=0.0)
