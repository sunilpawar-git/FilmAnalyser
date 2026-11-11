"""Extractor registry (open/closed): new extractors register themselves; nothing here changes."""

import re
from collections.abc import Iterator

from filmanalyser.core.extractor import Extractor

_NAME = re.compile(r"^[a-z][a-z0-9_]*$")


class ExtractorRegistry:
    """Ordered collection of extractors, keyed by unique name."""

    def __init__(self) -> None:
        self._items: dict[str, Extractor] = {}

    def register(self, extractor: Extractor) -> Extractor:
        if not _NAME.match(extractor.name):
            raise ValueError(f"invalid extractor name: {extractor.name!r}")
        if extractor.version < 1:
            raise ValueError(f"invalid extractor version: {extractor.version}")
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


REGISTRY = ExtractorRegistry()
