"""Single source of truth for tunable constants. Thresholds are added here as phases need them."""

from dataclasses import dataclass

from filmanalyser.core.errors import InputError


@dataclass(frozen=True)
class Config:
    """Immutable run configuration; defaults come from the product contract."""

    chunk_seconds: float = 60.0  # README: the film is streamed in 60 s chunks
    ram_budget_mb: int = 2048  # ACCEPTANCE: peak RAM must stay under 2 GB

    def __post_init__(self) -> None:
        for name in ("chunk_seconds", "ram_budget_mb"):
            if getattr(self, name) <= 0:
                raise InputError(f"{name} must be positive")
