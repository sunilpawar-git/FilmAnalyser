"""The feature schema is frozen for the MVP (ACCEPTANCE, Quality gates): the extractors, their
versions and features, and the schema version they hash to, are pinned to
`tests/golden/feature_schema.json`. Changing any of them fails here, which makes the change a
deliberate one: bump the extractor, update the golden file and add a DECISIONS entry, because every
stored run becomes unreadable.

To refresh after a deliberate change: `uv run python -m tests.unit.test_schema_frozen`."""

import json
import sys
from pathlib import Path
from typing import Any

from filmanalyser.extractors.registry import discover
from filmanalyser.pipeline.runner import schema_for

GOLDEN = Path(__file__).resolve().parents[1] / "golden" / "feature_schema.json"


def _current() -> dict[str, Any]:
    schema = schema_for(discover())
    return {
        "version": schema.version,
        "extractors": [[e.name, e.version, list(e.features)] for e in schema.extractors],
    }


def test_the_extractors_and_their_features_are_the_frozen_ones() -> None:
    golden = json.loads(GOLDEN.read_text(encoding="utf-8"))
    assert _current()["extractors"] == golden["extractors"]


def test_the_schema_version_is_the_frozen_one() -> None:
    golden = json.loads(GOLDEN.read_text(encoding="utf-8"))
    assert _current()["version"] == golden["version"]


if __name__ == "__main__":  # pragma: no cover
    json.dump(_current(), sys.stdout, indent=1)
    sys.stdout.write("\n")
