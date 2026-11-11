"""The feature schema is the single source of truth for names, types and version (DECISIONS #7)."""

import math
from collections.abc import Callable
from typing import Any

import pyarrow as pa
import pytest

from filmanalyser.core.errors import StorageError
from filmanalyser.storage.schema import (
    LAYOUT_VERSION,
    ExtractorColumns,
    FeatureSchema,
    chunk_file_name,
)
from tests.fixtures.store import make_schema, outputs


def test_columns_are_prefixed_by_extractor_and_follow_declaration_order() -> None:
    assert make_schema().columns == (
        "shot_cuts.cut_count",
        "shot_cuts.mean_shot_s",
        "color.brightness",
    )


def test_arrow_schema_has_fixed_types_and_no_nulls() -> None:
    schema = make_schema().arrow_schema()
    assert schema.names == [
        "chunk_index",
        "start_s",
        "end_s",
        "shot_cuts.cut_count",
        "shot_cuts.mean_shot_s",
        "color.brightness",
    ]
    assert schema.field("chunk_index").type == pa.int32()
    assert all(schema.field(n).type == pa.float64() for n in schema.names[1:])
    assert not any(f.nullable for f in schema)


def test_version_travels_in_the_parquet_metadata() -> None:
    schema = make_schema()
    meta = schema.arrow_schema().metadata
    assert meta[b"filmanalyser.feature_version"].decode() == schema.version
    assert meta[b"filmanalyser.layout_version"].decode() == str(LAYOUT_VERSION)


def test_version_is_stable_golden() -> None:
    """If this changes, every stored feature file becomes incompatible: that must be deliberate."""
    assert make_schema().version == (
        "bfeb3283a2d960f3ed8756cc02de8ec75ca1a13d12a1ee0f50fda182fac32d45"
    )


@pytest.mark.parametrize(
    "other",
    [
        make_schema(cuts_version=2),  # an extractor changed its output
        make_schema(extra_feature=True),  # a feature was added
        FeatureSchema(  # a feature was renamed
            (
                ExtractorColumns("shot_cuts", 1, ("cut_count", "avg_shot_s")),
                ExtractorColumns("color", 1, ("brightness",)),
            )
        ),
        FeatureSchema(  # extractor order is part of the layout
            (
                ExtractorColumns("color", 1, ("brightness",)),
                ExtractorColumns("shot_cuts", 1, ("cut_count", "mean_shot_s")),
            )
        ),
    ],
)
def test_any_change_gives_a_different_version(other: FeatureSchema) -> None:
    assert other.version != make_schema().version


def test_equal_schemas_have_equal_versions() -> None:
    assert make_schema().version == make_schema().version


@pytest.mark.parametrize(
    "extractors",
    [
        (),  # nothing to store
        (ExtractorColumns("Bad Name", 1, ("a",)),),
        (ExtractorColumns("ok", 1, ("has.dot",)),),
        (ExtractorColumns("ok", 0, ("a",)),),
        (ExtractorColumns("ok", 1, ()),),
        (ExtractorColumns("ok", 1, ("a", "a")),),
        (ExtractorColumns("ok", 1, ("a",)), ExtractorColumns("ok", 2, ("b",))),
    ],
)
def test_invalid_schemas_are_rejected(extractors: tuple[ExtractorColumns, ...]) -> None:
    with pytest.raises(StorageError) as caught:
        FeatureSchema(extractors)
    assert caught.value.key == "error.storage.bad_schema"


def test_row_flattens_outputs_into_column_order() -> None:
    row = make_schema().row(outputs(3))
    assert list(row) == list(make_schema().columns)
    assert row["shot_cuts.cut_count"] == 3.0
    assert row["color.brightness"] == pytest.approx(0.3)


@pytest.mark.parametrize(
    ("mutate", "name"),
    [
        (lambda o: o.pop("color"), "color"),  # an extractor is missing
        (lambda o: o.update(stray={"x": 1.0}), "stray"),  # an unknown extractor
        (lambda o: o["color"].pop("brightness"), "color.brightness"),
        (lambda o: o["color"].update(hue=1.0), "color.hue"),
        (lambda o: o["color"].update(brightness=math.nan), "color.brightness"),
        (lambda o: o["color"].update(brightness=math.inf), "color.brightness"),
        (lambda o: o["color"].update(brightness="0.5"), "color.brightness"),
        (lambda o: o["color"].update(brightness=True), "color.brightness"),
    ],
)
def test_row_rejects_outputs_that_do_not_match_the_schema(
    mutate: Callable[[dict[str, dict[str, Any]]], object], name: str
) -> None:
    given: dict[str, dict[str, Any]] = {k: dict(v) for k, v in outputs(0).items()}
    mutate(given)
    with pytest.raises(StorageError) as caught:
        make_schema().row(given)
    assert caught.value.key == "error.storage.bad_features"
    assert caught.value.fields == {"name": name}


def test_chunk_file_names_are_fixed_width_and_sortable() -> None:
    assert chunk_file_name(7) == "chunk_000007.parquet"
    assert sorted(chunk_file_name(i) for i in (10, 9, 100)) == [
        chunk_file_name(9),
        chunk_file_name(10),
        chunk_file_name(100),
    ]


@pytest.mark.parametrize("bad", [-1, True, 1.5, "3"])
def test_chunk_file_name_rejects_non_indexes(bad: object) -> None:
    with pytest.raises(StorageError):
        chunk_file_name(bad)  # type: ignore[arg-type]
