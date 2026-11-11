"""The Extractor protocol: the one interface every feature extractor implements.

Phase 1 fixes the shape (name, version, extract). Phase 2 narrows `chunk` from `object` to the
`Chunk` type once the decoder defines it; that is a deliberate, versioned contract change.
"""

from collections.abc import Mapping
from typing import Protocol, runtime_checkable


@runtime_checkable
class Extractor(Protocol):
    @property
    def name(self) -> str:
        """Unique snake_case identifier; also the feature-column prefix."""

    @property
    def version(self) -> int:
        """Bumped whenever the extractor's output changes (features are versioned)."""

    def extract(self, chunk: object) -> Mapping[str, float]:
        """Compute compact features for one chunk."""
