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
- Storage: an output directory holds `manifest.json` and one Parquet file per chunk, written atomically.
  The manifest records the finished chunks, keyed by the film's hash, the feature version and the chunk
  settings. A run killed mid-film resumes at the first unfinished chunk without decoding the finished
  ones; results from different inputs, extractor versions or settings are rejected, never mixed.

## Stack
Python 3.11+, ffmpeg, NumPy, Parquet (`pyarrow`), Jinja2 (report). OpenCV, librosa, ONNX Runtime and `ruptures` arrive with their phases; shot cuts and letterboxing use NumPy alone (DECISIONS #51). FastAPI + web UI + Tauri packaging are post-MVP.

## MVP metrics
Shot cuts and average shot length, cut-rate curve, colour palette and brightness, loudness profile, speech/music/silence ratio, tension curve, act-break detection, flagged timestamps.

## Usage
```sh
filmanalyser film.mp4 --out work/film        # writes work/film/report.html
filmanalyser film.mp4 --out work/film -v     # also prints the structured progress events
```
Repeating a run with the same `--out` folder resumes at the first unfinished chunk. Exit codes:
`0` success, `1` internal error, `2` invalid input or setting, `3` the film could not be decoded
(or ffmpeg is missing, or voice separation failed), `4` a model file is missing or failed its
integrity check, `5` the stored features are damaged or belong to another film. The report
is one static HTML page (no scripts, no network); it shows the hard cuts per minute over the film.

### Optional: speech under loud music (stereo films)
A 5.1 film's dialogue is read from its centre channel. A stereo or mono film has no dialogue
channel, so speech under loud music is often missed. `--separate-voices` adds voice separation
(Demucs htdemucs, MIT) on the chunks whose background is loud, and a window counts as speech when
either the mix or the separated voice says so (DECISIONS #88). Setup, once:
```sh
uv tool install demucs==4.1.0 # the separation tool (brings PyTorch; not a project dependency)
make separation-model         # the pinned model (84 MB) into ~/.cache/filmanalyser/htdemucs
filmanalyser film.mp4 --out work/film --separate-voices
```
It is off by default, never downloads at run time (the model folder is verified against
`SEPARATION.sha256` first), and is skipped on 5.1 films. A different folder can be given with
`--separation-model` or `FILMANALYSER_SEPARATION_MODEL`. Stores made with and without it are kept
apart (it is part of the store key).

## Development
```sh
make sync      # locked environment (uv)
make hooks     # pre-commit + Conventional Commits check
make check     # the build: lint, mypy --strict, tests + coverage, security, wheel, guard self-test
make nightly   # slow checks (long-film memory): run by the nightly workflow
make real-clip # real-footage kill-and-resume test: FILMANALYSER_REAL_CLIP=/path/to/clip make real-clip
make models   # fetch the pinned Silero VAD model (setup only; the app never downloads)
make separation-model  # opt-in: the pinned voice-separation model (needs demucs to use)
make separation-check  # opt-in: real separation test (demucs on PATH + the model)
```
The real-footage test never runs inside `make check` (DECISIONS #53); the clip stays outside the repo.
### Requirements
- `uv`, `make`, `gitleaks`
- **`ffmpeg` and `ffprobe` on `PATH`** (decoding and probing). Not a Python package, so install it
  yourself: `brew install ffmpeg` (macOS) or `apt install ffmpeg` (Debian/Ubuntu). Developed and
  tested on ffmpeg 9.0.2; CI pins 6.0.1 on Linux. Without it the integration tests fail
  loudly and the tool exits with a clear "ffmpeg not found" message.

## Docs
- `EXECUTION_PLAN.md`: phases, rules, enforcement
- `docs/handoff/`: per-phase handoff notes
- `docs/BRANCH_PROTECTION.md`: GitHub setup for `main`
- `ACCEPTANCE.md`: what "done" means
- `DECISIONS.md`: log of choices
- `BACKLOG.md`: ideas parked outside the current scope
