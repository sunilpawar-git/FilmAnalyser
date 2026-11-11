"""Shared builders for storage tests: a small schema, matching outputs and a run key."""

from collections.abc import Mapping
from pathlib import Path

from filmanalyser.core.config import Config
from filmanalyser.storage.feature_store import FeatureStore
from filmanalyser.storage.manifest import RunKey
from filmanalyser.storage.schema import ExtractorColumns, FeatureSchema

CONFIG = Config(chunk_seconds=10.0, overlap_seconds=1.0, analysis_fps=10.0, frame_width=64)
INPUT_HASH = "a" * 64


def make_schema(*, cuts_version: int = 1, extra_feature: bool = False) -> FeatureSchema:
    cuts = ("cut_count", "mean_shot_s", *(("extra",) if extra_feature else ()))
    return FeatureSchema(
        (
            ExtractorColumns("shot_cuts", cuts_version, cuts),
            ExtractorColumns("color", 1, ("brightness",)),
        )
    )


def outputs(index: int, *, extra_feature: bool = False) -> Mapping[str, Mapping[str, float]]:
    cuts = {"cut_count": float(index), "mean_shot_s": 2.5 + index}
    if extra_feature:
        cuts["extra"] = 0.0
    return {"shot_cuts": cuts, "color": {"brightness": 0.1 * index}}


def make_key(schema: FeatureSchema | None = None, input_hash: str = INPUT_HASH) -> RunKey:
    return RunKey(input_hash, (schema or make_schema()).version, CONFIG.geometry())


def fill(store: FeatureStore, count: int) -> None:
    """Append `count` chunks of ten seconds each, using `outputs`."""
    for i in range(count):
        store.append(i, i * 10.0, (i + 1) * 10.0, outputs(i))


def tamper(path: Path, offset: int = 20) -> None:
    """Flip one byte of a file (silent bit rot)."""
    data = bytearray(path.read_bytes())
    data[offset] ^= 0xFF
    path.write_bytes(bytes(data))
