"""The registry is open/closed: a new extractor is found by discovery without touching existing
modules, and every shipped extractor emits exactly the features it declares."""

import dataclasses
import sys
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import get_type_hints

import numpy as np
import pytest

from filmanalyser.core.chunk import Audio, Chunk
from filmanalyser.core.config import AUDIO_RATE, VOICE_WINDOW
from filmanalyser.core.extractor import Extractor
from filmanalyser.extractors.registry import ExtractorRegistry, discover


def _chunk() -> Chunk:
    frames = np.zeros((2, 2, 2, 3), dtype=np.uint8)
    return Chunk(index=0, start_s=0.0, end_s=0.2, fps=10.0, frames=frames, context_frames=0)


@dataclass(frozen=True)
class DummyExtractor:
    name: str = "dummy"
    version: int = 1
    features: tuple[str, ...] = ("seen",)
    needs_audio: bool = False

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


@pytest.mark.parametrize("features", [(), ("a", "a"), ("Bad",)])
def test_invalid_feature_declaration_rejected(features: tuple[str, ...]) -> None:
    with pytest.raises(ValueError, match="features"):
        ExtractorRegistry().register(DummyExtractor(features=features))


def test_unknown_name_raises() -> None:
    with pytest.raises(LookupError, match="nope"):
        ExtractorRegistry().get("nope")


def test_registries_are_independent() -> None:
    first, second = ExtractorRegistry(), ExtractorRegistry()
    first.register(DummyExtractor())
    assert second.names() == ()


def test_protocol_contract_takes_a_chunk_and_declares_features() -> None:
    """DECISIONS #25 narrowed `chunk` to Chunk; #49 adds the declared feature names."""
    assert get_type_hints(Extractor.extract)["chunk"] is Chunk
    assert "features" in vars(Extractor)  # declared on the protocol, so every extractor has it


def test_discovery_finds_the_shipped_extractors_in_name_order() -> None:
    assert discover().names() == ("color", "loudness", "shot_cuts", "speech_music")


def test_helper_modules_are_not_extractors() -> None:
    assert "letterbox" not in discover().names()


def test_every_shipped_extractor_emits_exactly_its_declared_features() -> None:
    for extractor in discover():
        chunk = _audio_chunk() if extractor.needs_audio else _textured_chunk()
        out = extractor.extract(chunk)
        assert set(out) == set(extractor.features), extractor.name
        assert all(np.isfinite(v) for v in out.values()), extractor.name


def _textured_chunk() -> Chunk:
    rng = np.random.default_rng(7)
    frames = rng.integers(0, 256, size=(12, 18, 16, 3), dtype=np.uint8)
    return Chunk(0, 0.0, 1.2, 10.0, frames, context_frames=0)


def _audio_chunk() -> Chunk:
    """The textured chunk with a noisy 16 kHz track and its voice probabilities (what the runner
    attaches before audio extractors run)."""
    chunk = _textured_chunk()
    rng = np.random.default_rng(7)
    samples = rng.uniform(-0.5, 0.5, size=(round(1.2 * AUDIO_RATE), 1)).astype(np.float32)
    voice = np.full(len(samples) // VOICE_WINDOW, 0.2, dtype=np.float32)
    audio = Audio(rate=AUDIO_RATE, start_s=0.0, samples=samples, voice=voice)
    return dataclasses.replace(chunk, audio=audio, audio_hires=audio)


def test_a_new_extractor_module_is_discovered_without_editing_existing_ones(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Open/closed, proven: a module dropped into a package is registered; nothing else changes."""
    package = f"pluginpkg_{uuid.uuid4().hex}"
    root = tmp_path / package
    root.mkdir()
    (root / "__init__.py").write_text("", encoding="utf-8")
    (root / "zz_new.py").write_text(
        "from dataclasses import dataclass\n"
        "@dataclass(frozen=True)\n"
        "class New:\n"
        "    name = 'zz_new'\n"
        "    version = 1\n"
        "    features = ('one',)\n"
        "    def extract(self, chunk):\n"
        "        return {'one': 1.0}\n"
        "EXTRACTOR = New()\n",
        encoding="utf-8",
    )
    (root / "_helper.py").write_text("VALUE = 1\n", encoding="utf-8")  # no EXTRACTOR: ignored
    monkeypatch.syspath_prepend(str(tmp_path))
    try:
        assert discover(package).names() == ("zz_new",)
    finally:
        for name in [m for m in sys.modules if m == package or m.startswith(package + ".")]:
            del sys.modules[name]
