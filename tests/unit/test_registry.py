"""The registry is open/closed: a new extractor registers without touching existing modules."""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import get_type_hints

import numpy as np
import pytest

from filmanalyser.core.chunk import Chunk
from filmanalyser.core.extractor import Extractor
from filmanalyser.extractors.registry import REGISTRY, ExtractorRegistry


def _chunk() -> Chunk:
    frames = np.zeros((2, 2, 2, 3), dtype=np.uint8)
    return Chunk(index=0, start_s=0.0, end_s=0.2, fps=10.0, frames=frames, context_frames=0)


@dataclass(frozen=True)
class DummyExtractor:
    name: str = "dummy"
    version: int = 1

    def extract(self, chunk: Chunk) -> Mapping[str, float]:
        return {"seen": float(len(chunk.core))}


def test_dummy_satisfies_the_extractor_protocol() -> None:
    assert isinstance(DummyExtractor(), Extractor)


def test_dummy_registers_and_is_retrievable() -> None:
    registry = ExtractorRegistry()
    dummy = DummyExtractor()
    assert registry.register(dummy) is dummy
    assert registry.get("dummy") is dummy
    assert registry.get("dummy").extract(_chunk()) == {"seen": 2.0}


def test_registration_order_is_preserved() -> None:
    registry = ExtractorRegistry()
    for name in ("b", "a", "c"):
        registry.register(DummyExtractor(name=name))
    assert registry.names() == ("b", "a", "c")
    assert [e.name for e in registry] == ["b", "a", "c"]
    assert len(registry) == 3


def test_duplicate_name_rejected() -> None:
    registry = ExtractorRegistry()
    registry.register(DummyExtractor())
    with pytest.raises(ValueError, match="already registered"):
        registry.register(DummyExtractor(version=2))


@pytest.mark.parametrize("name", ["", "Bad", "1abc", "has space", "dash-ed"])
def test_invalid_name_rejected(name: str) -> None:
    with pytest.raises(ValueError, match="name"):
        ExtractorRegistry().register(DummyExtractor(name=name))


@pytest.mark.parametrize("version", [0, -1])
def test_invalid_version_rejected(version: int) -> None:
    with pytest.raises(ValueError, match="version"):
        ExtractorRegistry().register(DummyExtractor(version=version))


def test_unknown_name_raises() -> None:
    with pytest.raises(LookupError, match="nope"):
        ExtractorRegistry().get("nope")


def test_registries_are_independent() -> None:
    first, second = ExtractorRegistry(), ExtractorRegistry()
    first.register(DummyExtractor())
    assert second.names() == ()


def test_default_registry_starts_empty() -> None:
    assert REGISTRY.names() == ()


def test_protocol_contract_takes_a_chunk() -> None:
    """DECISIONS #25: the Phase 1 `object` placeholder is narrowed to Chunk."""
    hints = get_type_hints(Extractor.extract)
    assert hints["chunk"] is Chunk
