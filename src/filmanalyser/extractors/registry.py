"""Extractor registry (open/closed, DECISIONS #50): every module of this package that defines a
module-level `EXTRACTOR` is an extractor. `discover()` finds them, so adding an extractor means
adding one module and touching nothing else."""

import importlib
import pkgutil
import re
from collections.abc import Iterator

from filmanalyser.core.extractor import Extractor

EXTRACTORS_PACKAGE = "filmanalyser.extractors"
_NAME = re.compile(r"^[a-z][a-z0-9_]*$")  # snake_case: a feature column prefix and a file-safe id


class ExtractorRegistry:
    """Ordered collection of extractors, keyed by unique name."""

    def __init__(self) -> None:
        self._items: dict[str, Extractor] = {}

    def register(self, extractor: Extractor) -> Extractor:
        if not _valid_name(extractor.name):
            raise ValueError(f"invalid extractor name: {extractor.name!r}")
        if extractor.version < 1:
            raise ValueError(f"invalid extractor version: {extractor.version}")
        if not _valid_features(extractor.features):
            raise ValueError(f"invalid features for {extractor.name}: {extractor.features!r}")
        if extractor.name in self._items:
            raise ValueError(f"extractor already registered: {extractor.name}")
        self._items[extractor.name] = extractor
        return extractor

    def get(self, name: str) -> Extractor:
        try:
            return self._items[name]
        except KeyError:
            raise LookupError(f"unknown extractor: {name}") from None

    def names(self) -> tuple[str, ...]:
        return tuple(self._items)

    def __iter__(self) -> Iterator[Extractor]:
        return iter(self._items.values())

    def __len__(self) -> int:
        return len(self._items)


def _valid_name(name: str) -> bool:
    return _NAME.match(name) is not None


def _valid_features(features: tuple[str, ...]) -> bool:
    return (
        bool(features) and len(set(features)) == len(features) and all(map(_valid_name, features))
    )


def discover(package: str = EXTRACTORS_PACKAGE) -> ExtractorRegistry:
    """A registry of every extractor module in `package`, in module-name order. Modules whose
    names start with an underscore, and modules without an `EXTRACTOR`, are not extractors."""
    registry = ExtractorRegistry()
    pkg = importlib.import_module(package)
    for info in sorted(pkgutil.iter_modules(pkg.__path__), key=lambda m: m.name):
        if info.name.startswith("_"):
            continue
        extractor = getattr(importlib.import_module(f"{package}.{info.name}"), "EXTRACTOR", None)
        if extractor is not None:
            registry.register(extractor)
    return registry
