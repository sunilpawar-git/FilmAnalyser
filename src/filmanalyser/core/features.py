"""Column and feature names shared by the store (storage/), the view model (report/) and the
extractors. Defined once here because `core/` is the only layer every other layer may import
(DECISIONS #28, EXECUTION_PLAN section 0: names defined once)."""

CHUNK_INDEX = "chunk_index"
START_S = "start_s"  # film time at which a chunk's core window starts
END_S = "end_s"  # film time at which it ends (exclusive)
SHOT_CUTS = "shot_cuts"  # the shot_cuts extractor's name
CUT_COUNT = f"{SHOT_CUTS}.cuts"  # hard cuts in a chunk's core window
