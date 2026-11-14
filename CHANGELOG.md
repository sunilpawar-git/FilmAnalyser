## Unreleased

### Feat

- **scripts**: real-film validation with the owner's act-break rules
- **cli**: full command with defaults, --fresh, --version and every exit code
- **report**: self-contained HTML report with inline SVG charts
- **report**: view model over the timeline analysis
- **report**: display text, chart geometry and resource keys
- **analysis**: report zones a short film is too short to judge
- **analysis**: pacing plateaus, tension peak and flags
- **analysis**: act breaks per the owner's specification
- **analysis**: timeline series, z-scores and smoothing with missing values
- **speech**: opt-in voice separation where music is loud
- **speech**: hear 5.1 dialogue on the centre channel
- **shots**: calm-second cut rule and blend test for transitions
- **shots**: gradual transitions, merged cuts, and a corrected cut measurement
- **speech**: close P4-3, P4-4, P5-1, P5-2 with measured evidence and a limitations list
- **audio**: measure loudness and true peak at 48 kHz (BS.1770's own rate)
- **eval**: tooling to measure the blocked open items against hand labels
- **audio**: align audio on the container clock, surround weights, true peak
- **audio**: loudness and speech/music/silence on a decoded audio path
- **ci**: nightly benchmark record and job summary
- **extractors**: phase 4 - shot cuts, colour, walking skeleton, P3-1 resume fix
- **storage**: phase 3 - versioned Parquet store, manifest, kill-and-resume
- **decoder**: phase 2 - core contracts and streaming decoder
- **foundation**: phase 1 - guardrails, resources, registry skeleton, CI

### Fix

- **loudness**: bound the memory of 5.1 loudness with block convolution
- **telemetry**: measure the program's own peak memory on Linux
- **loudness**: check the meter against EBU Tech 3341 and drop window-edge overshoot
- **test**: write the synthetic audio track as QuickTime PCM

### Refactor

- **scripts**: timeline_report uses the report's clock text
