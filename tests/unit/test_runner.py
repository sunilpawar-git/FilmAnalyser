"""The pipeline's pure rules: the schema is built from declared features, and the pipeline refuses
a configuration the extractors cannot run under (no overlap means a missed boundary cut)."""

from collections.abc import Mapping
from dataclasses import dataclass

import pytest

from filmanalyser.core.chunk import Chunk
from filmanalyser.core.config import Config
from filmanalyser.core.errors import InputError
from filmanalyser.extractors.registry import ExtractorRegistry
from filmanalyser.pipeline.runner import schema_for, validate_for_pipeline


@dataclass(frozen=True)
class Stub:
    name: str
    features: tuple[str, ...]
    version: int = 1

    def extract(self, chunk: Chunk) -> Mapping[str, float]:
        return dict.fromkeys(self.features, 0.0)


def _registry(*stubs: Stub) -> ExtractorRegistry:
    registry = ExtractorRegistry()
    for stub in stubs:
        registry.register(stub)
    return registry


def test_schema_columns_follow_registration_order_and_declared_features() -> None:
    registry = _registry(Stub("shot_cuts", ("cuts", "max_diff")), Stub("color", ("brightness",)))
    schema = schema_for(registry)
    assert schema.columns == ("shot_cuts.cuts", "shot_cuts.max_diff", "color.brightness")
    assert [e.name for e in schema.extractors] == ["shot_cuts", "color"]


def test_adding_a_feature_changes_the_schema_version() -> None:
    before = schema_for(_registry(Stub("color", ("brightness",))))
    after = schema_for(_registry(Stub("color", ("brightness", "warmth"))))
    assert before.version != after.version


def test_a_bumped_extractor_version_changes_the_schema_version() -> None:
    before = schema_for(_registry(Stub("color", ("brightness",), version=1)))
    after = schema_for(_registry(Stub("color", ("brightness",), version=2)))
    assert before.version != after.version


def test_an_empty_registry_is_refused_by_the_schema() -> None:
    with pytest.raises(Exception, match="extractors"):
        schema_for(ExtractorRegistry())


def test_the_default_configuration_is_accepted() -> None:
    validate_for_pipeline(Config())


def test_zero_overlap_is_refused_because_a_boundary_cut_would_be_missed() -> None:
    with pytest.raises(InputError) as caught:
        validate_for_pipeline(Config(overlap_seconds=0.0))
    assert caught.value.key == "error.input.bad_setting"
    assert caught.value.fields == {"name": "overlap_seconds"}
