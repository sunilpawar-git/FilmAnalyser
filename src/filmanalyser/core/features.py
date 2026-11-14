"""Column and feature names shared by the store (storage/), the analysis (analysis/), the view
model (report/) and the extractors. Defined once here because `core/` is the only layer every
other layer may import (DECISIONS #28, EXECUTION_PLAN section 0: names defined once)."""

CHUNK_INDEX = "chunk_index"
START_S = "start_s"  # film time at which a chunk's core window starts
END_S = "end_s"  # film time at which it ends (exclusive)
SHOT_CUTS = "shot_cuts"  # the shot_cuts extractor's name
CUT_COUNT = f"{SHOT_CUTS}.cuts"  # hard cuts in a chunk's core window
CUT_RATE = "cut_rate"  # derived by the analysis: cuts and gradual transitions per minute
GRADUAL_COUNT = f"{SHOT_CUTS}.gradual"  # gradual transitions (dissolves, fades) in the window
LOUDNESS = "loudness"
LUFS = f"{LOUDNESS}.integrated_lufs"
TRUE_PEAK = f"{LOUDNESS}.true_peak_dbfs"
SPEECH_MUSIC = "speech_music"
SILENCE_RATIO = f"{SPEECH_MUSIC}.silence_ratio"
SPEECH_RATIO = f"{SPEECH_MUSIC}.speech_ratio"
TONAL_RATIO = f"{SPEECH_MUSIC}.tonal_ratio"
COLOR = "color"
BRIGHTNESS = f"{COLOR}.brightness"
CONTRAST = f"{COLOR}.contrast"
COLOURFULNESS = f"{COLOR}.colourfulness"
WARMTH = f"{COLOR}.warmth"
# The analysis reads these store columns (the letterbox share is left out: a change of aspect ratio
# would swamp every other feature, DECISIONS #90). A film without audio simply lacks the audio ones.
VIDEO_STATE_COLUMNS = (BRIGHTNESS, CONTRAST, COLOURFULNESS, WARMTH)
AUDIO_STATE_COLUMNS = (LUFS, SPEECH_RATIO, TONAL_RATIO, SILENCE_RATIO)
STATE_FEATURES = (CUT_RATE, *AUDIO_STATE_COLUMNS, *VIDEO_STATE_COLUMNS)  # the film state, in order
