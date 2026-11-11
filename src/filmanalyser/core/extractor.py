"""The Extractor protocol: the one interface every feature extractor implements.

Phase 1 fixed the shape (name, version, extract); Phase 2 narrowed `chunk` from `object` to
`Chunk` (DECISIONS #25, #34).
"""

from collections.abc import Mapping
from typing import Protocol, runtime_checkable

from filmanalyser.core.chunk import Chunk


@runtime_checkable
class Extractor(Protocol):
    @property
    def name(self) -> str:
        """Unique snake_case identifier; also the feature-column prefix."""

    @property
    def version(self) -> int:
        """Bumped whenever the extractor's output changes (features are versioned)."""

    def extract(self, chunk: Chunk) -> Mapping[str, float]:
        """Compute compact features for one chunk."""
