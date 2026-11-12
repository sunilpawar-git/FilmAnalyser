"""Single source of truth for tunable constants. Thresholds are added here as phases need them."""

from dataclasses import dataclass

from filmanalyser.core.chunk import frames_for
from filmanalyser.core.errors import InputError

# Security bounds on external tools (SSOT; consumed by media/). Not per-run settings.
STDERR_LIMIT_BYTES = 4096  # tool diagnostics kept; anything older is dropped
PROBE_TIMEOUT_S = 30.0  # ffprobe must answer within this
PROBE_MAX_OUTPUT_BYTES = 1024 * 1024  # a probe answer is a few hundred bytes; more is wrong

# Feature store bounds (SSOT; consumed by storage/). A chunk file holds one row of a few dozen
# numbers and a manifest a hash per chunk, so anything this large is damaged or hostile.
STORE_MAX_FILE_BYTES = 4 * 1024 * 1024
HASH_BLOCK_BYTES = 1024 * 1024  # the input film is hashed in blocks this big, never loaded whole

# Video features (SSOT; consumed by extractors/). Chosen against synthetic clips with known ground
# truth (DECISIONS #57); any change is a new decision.
CUT_DISTANCE = 0.40  # histogram distance between consecutive frames (0..1) that counts as a cut
HIST_BINS = 16  # soft histogram bins per colour channel (a pixel splits between its two nearest)
LETTERBOX_LUMA = 0.06  # a row darker than this (0..1, mean luma over the chunk) is a black bar
LUMA_WEIGHTS = (0.2126, 0.7152, 0.0722)  # ITU-R BT.709 luma coefficients for R, G, B
EXTRACT_BUDGET_FRACTION = (
    0.25  # extraction may take this share of the film's duration (45 min / 3 h)
)

# The settings that decide what a chunk contains: part of the key a stored run is cached by.
GEOMETRY_FIELDS = ("chunk_seconds", "overlap_seconds", "analysis_fps", "frame_width")

_POSITIVE = ("chunk_seconds", "ram_budget_mb", "analysis_fps", "frame_width")


@dataclass(frozen=True)
class Config:
    """Immutable run configuration; defaults come from the product contract."""

    chunk_seconds: float = 60.0  # README: the film is streamed in 60 s chunks
    ram_budget_mb: int = 2048  # ACCEPTANCE: peak RAM must stay under 2 GB
    overlap_seconds: float = 2.0  # context a chunk reuses from the previous one (state carry)
    analysis_fps: float = 12.0  # decoder output rate; fixes cut-timing resolution (DECISIONS #33)
    frame_width: int = 160  # decoder output width in px (DECISIONS #33); height keeps the aspect

    def __post_init__(self) -> None:
        for name in _POSITIVE:
            if getattr(self, name) <= 0:
                raise _invalid(name)
        if not 0 <= self.overlap_seconds < self.chunk_seconds:
            raise _invalid("overlap_seconds")
        if round(self.chunk_seconds * self.analysis_fps) < 1:
            raise _invalid("chunk_seconds")  # a chunk must hold at least one frame
        if self.frame_width % 2:
            raise _invalid("frame_width")  # video scaling needs even dimensions

    def geometry(self) -> dict[str, float]:
        """The `GEOMETRY_FIELDS` and their values: what stored features were computed under."""
        return {name: getattr(self, name) for name in GEOMETRY_FIELDS}

    @property
    def frames_per_chunk(self) -> int:
        return frames_for(self.chunk_seconds, self.analysis_fps)

    @property
    def overlap_frames(self) -> int:
        return round(self.overlap_seconds * self.analysis_fps)


def _invalid(name: str) -> InputError:
    return InputError(key="error.input.bad_setting", name=name)
