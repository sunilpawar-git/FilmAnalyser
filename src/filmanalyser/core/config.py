"""Single source of truth for tunable constants. Thresholds are added here as phases need them."""

from dataclasses import dataclass

from filmanalyser.core.chunk import MAX_AUDIO_CHANNELS, frames_for
from filmanalyser.core.errors import InputError

# Security bounds on external tools (SSOT; consumed by media/). Not per-run settings.
STDERR_LIMIT_BYTES = 4096  # tool diagnostics kept; anything older is dropped
PROBE_TIMEOUT_S = 30.0  # ffprobe must answer within this
PROBE_MAX_OUTPUT_BYTES = 1024 * 1024  # a probe answer is a few hundred bytes; more is wrong
MODEL_MAX_BYTES = 16 * 1024 * 1024  # the Silero model is 2.3 MB; a larger file is not it
AUDIO_TIMEOUT_S = 120.0  # one chunk of audio (60 s by default) decodes in well under a second

# Feature store bounds (SSOT; consumed by storage/). A chunk file holds one row of a few dozen
# numbers and a manifest a hash per chunk, so anything this large is damaged or hostile.
STORE_MAX_FILE_BYTES = 4 * 1024 * 1024
HASH_BLOCK_BYTES = 1024 * 1024  # the input film is hashed in blocks this big, never loaded whole

# Video features (SSOT; consumed by extractors/). Chosen against synthetic clips with known ground
# truth (DECISIONS #57); any change is a new decision.
CUT_DISTANCE = 0.40  # histogram distance between consecutive frames (0..1) that counts as a cut
HIST_BINS = 16  # soft histogram bins per colour channel (a pixel splits between its two nearest)
CUT_BAND_FLOOR = (
    0.20  # a smaller change is a cut too when the second around it is calm (DECISIONS #83)
)
CUT_CALM_P90 = 0.10  # calm: 90% of the frame changes in that second stay below this
CUT_CALM_RADIUS = 12  # frames either side that make up that second (12 fps)
GRADUAL_FLOOR = (
    0.05  # a frame distance above this is part of a possible gradual transition (DECISIONS #79)
)
GRADUAL_MIN_FRAMES = 4  # a gradual transition lasts at least this many analysis frames
GRADUAL_SUM = (
    0.5  # and its summed frame distances reach this (a dissolve measured about 1.2 per second)
)
GRADUAL_BLEND_RESIDUAL = 0.35  # a transition's frames must be blends of its ends (DECISIONS #84)
CUT_MERGE_FRAMES = 3  # cut spikes closer than this are one cut: the strongest is kept
LETTERBOX_LUMA = 0.06  # a row darker than this (0..1, mean luma over the chunk) is a black bar
LUMA_WEIGHTS = (0.2126, 0.7152, 0.0722)  # ITU-R BT.709 luma coefficients for R, G, B
EXTRACT_BUDGET_FRACTION = (
    0.25  # extraction may take this share of the film's duration (45 min / 3 h)
)

# Audio features (SSOT; consumed by media/ and extractors/). Chosen against synthetic clips with
# known ground truth (DECISIONS #60). Audio is decoded at AUDIO_RATE: Silero VAD's rate.
AUDIO_RATE = 16000  # Hz for speech (Silero VAD) and the classifier's windows
AUDIO_HIRES_RATE = 48000  # Hz for loudness and true peak: BS.1770's own rate (DECISIONS #72)
AUDIO_MAX_CHANNELS = MAX_AUDIO_CHANNELS  # up to 5.1 natively (DECISIONS #68); more is downmixed
FIVE_ONE_CHANNELS = 6  # a 5.1 track, in ffmpeg's order: L R C LFE Ls Rs
FIVE_ONE_CENTRE = 2  # its centre channel, where film dialogue is mixed (DECISIONS #86)
VOICE_WINDOW = 512  # samples per voice decision (32 ms at 16 kHz): the Silero window size
VOICE_CONTEXT = 64  # samples of the previous window the model reads with each window (Silero v5+)
SPEECH_PROB = 0.5  # voice probability at or above which a window is speech
SILENCE_DBFS = -50.0  # a window quieter than this (RMS, dBFS) is silence
MUSIC_FLATNESS = (
    0.2  # spectral flatness (0 pure tone, 1 white noise) below which non-speech is tonal
)
SEPARATION_BED_DBFS = -35.0  # opt-in voice separation runs on a chunk whose background is this loud
SEPARATION_BATCH = 10  # chunks per separation run (the model loads once per run)
SEPARATION_TIMEOUT_S = 3600.0  # one separation run must finish within this
SEPARATION_MAX_MODEL_BYTES = 256 * 1024 * 1024  # the htdemucs weights are 84 MB
LOUDNESS_BLOCK_S = 0.4  # BS.1770 gating block length
LOUDNESS_HOP_S = 0.1  # block hop (75% overlap)
LOUDNESS_OFFSET_LU = -0.691  # BS.1770 constant: loudness = offset + 10 log10(mean square)
LOUDNESS_ABS_GATE_LUFS = -70.0  # blocks quieter than this never count (also the silence floor)
LOUDNESS_REL_GATE_LU = -10.0  # then blocks more than this below the mean of the rest are dropped
PEAK_FLOOR_DBFS = -120.0  # the sample peak of digital silence

# Timeline analysis (SSOT; consumed by analysis/). Chosen on synthetic timelines with known change
# points and noise (DECISIONS #90 to #92); never calibrated on films with known act structure.
SECONDS_PER_MINUTE = 60.0  # the unit of a cut rate
TIMELINE_MIN_TAIL_FRACTION = 0.5  # a last chunk shorter than this share of a normal one is dropped
Z_EPSILON = 1e-9  # a series whose spread is below this is constant: its z-scores are all zero
ACT_SMOOTH_CHUNKS = 3  # centred moving average over this many chunks before comparing windows
ACT_WINDOW_CHUNKS = 5  # a boundary is scored on this many chunks before and after it
ACT_MIN_SCORE = 1.5  # a change score a break must exceed: noise tops out at 1.36, a step is 1.9+
ACT_MIN_GAP_CHUNKS = 10  # candidates closer than this are one: the strongest is kept
ACT_MAX_BREAKS = 2  # at most one break per zone, never more than this
ACT_ZONE_1 = (0.15, 0.40)  # share of the film where the first break may lie
ACT_ZONE_2 = (0.60, 0.90)  # and the second
ACT_ZONE_PRIORS = (0.25, 0.75)  # the classical positions: a tie-break only, never a reason
ACT_TIE_FRACTION = 0.05  # candidates within this share of the best score count as tied
ACT_TOP_FEATURES = 2  # features named as having moved most across a break
TENSION_SMOOTH_CHUNKS = 3  # the tension series is smoothed over this many chunks
TENSION_MIN_PEAK_Z = 3.0  # the tension peak must reach this many standard deviations (noise: 2.75)
PACING_PLATEAU_MIN_CHUNKS = 5  # a pacing plateau lasts at least this many chunks
PACING_PLATEAU_RANGE_Z = 0.5  # and its cut rate stays within this range (z units)
FLAG_OUTLIER_Z = 2.0  # a chunk this many standard deviations above the film is flagged
FLAG_SILENCE_RATIO = 0.9  # a chunk this silent (share of windows below SILENCE_DBFS) is flagged
FLAG_TRUE_PEAK_DBFS = 0.0  # a true peak at or above this clips on playback
FLAG_NO_CUT_CHUNKS = 3  # this many chunks in a row without a cut is a long take

# The settings that decide what a chunk contains: part of the key a stored run is cached by.
GEOMETRY_FIELDS = (
    "chunk_seconds",
    "overlap_seconds",
    "analysis_fps",
    "frame_width",
    "separate_voices",
)

_POSITIVE = ("chunk_seconds", "ram_budget_mb", "analysis_fps", "frame_width")


@dataclass(frozen=True)
class Config:
    """Immutable run configuration; defaults come from the product contract."""

    chunk_seconds: float = 60.0  # README: the film is streamed in 60 s chunks
    ram_budget_mb: int = 2048  # ACCEPTANCE: peak RAM must stay under 2 GB
    overlap_seconds: float = 2.0  # context a chunk reuses from the previous one (state carry)
    analysis_fps: float = 12.0  # decoder output rate; fixes cut-timing resolution (DECISIONS #33)
    frame_width: int = 160  # decoder output width in px (DECISIONS #33); height keeps the aspect
    separate_voices: bool = False  # opt-in voice separation where music is loud (DECISIONS #88)
    separation_model: str = ""  # folder of the pinned separation model (not part of the cache key)

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
        if self.separate_voices and not self.separation_model:
            raise _invalid("separation_model")  # separation needs its model folder

    def geometry(self) -> dict[str, float]:
        """The `GEOMETRY_FIELDS` and their values: what stored features were computed under."""
        return {name: float(getattr(self, name)) for name in GEOMETRY_FIELDS}  # bools as 1.0 / 0.0

    @property
    def frames_per_chunk(self) -> int:
        return frames_for(self.chunk_seconds, self.analysis_fps)

    @property
    def overlap_frames(self) -> int:
        return round(self.overlap_seconds * self.analysis_fps)


def _invalid(name: str) -> InputError:
    return InputError(key="error.input.bad_setting", name=name)
