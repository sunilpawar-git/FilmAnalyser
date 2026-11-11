# FilmAnalyser

## Product (one sentence)
A local tool that turns an mp4 film (2-3 hrs) into a craft-analysis report, streaming it in chunks and using under 2 GB RAM.

## What it is
A **craft analyser**: it measures form (editing rhythm, colour, light, motion, sound, structure) and flags notable or problematic sections with timestamps.

## Non-goals (MVP)
- No judgement of story, acting, theme, or emotional impact.
- No absolute "quality score". Any rating is relative and comes later.
- No UI (CLI + static HTML report only).
- No cloud, no uploads. Everything runs locally.
- No model training.
- No LLM requirement. Prose is templated; an optional small LLM may narrate metrics later.

Anything not listed here needs an entry in `DECISIONS.md` before it is built.

## Architecture
```
mp4 --ffmpeg pipe--> 60s chunk --> extractors --> append to Parquet --> discard chunk
                                                        |
                                    whole-film timeline (few MB)
                                                        v
                                 timeline analysis --> HTML report
```
- Memory depends on chunk size, not film length.
- Extractors share one interface: `extract(chunk) -> dict`.
- Features are versioned; re-analysis never requires re-decoding.

## Stack
Python 3.11+, ffmpeg, OpenCV, librosa, ONNX Runtime, NumPy/pandas, `ruptures`, Parquet. FastAPI + web UI + Tauri packaging are post-MVP.

## MVP metrics
Shot cuts and average shot length, cut-rate curve, colour palette and brightness, loudness profile, speech/music/silence ratio, tension curve, act-break detection, flagged timestamps.

## Docs
- `ACCEPTANCE.md`: what "done" means
- `DECISIONS.md`: log of choices
- `BACKLOG.md`: ideas parked outside the current scope
