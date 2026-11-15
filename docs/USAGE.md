# Using filmanalyser

`filmanalyser film.mp4` analyses a film on your own machine and writes a static HTML report.
Nothing is uploaded and no network is used at run time.

## Install

```sh
uv sync --locked          # from a checkout; or install the wheel from a release
brew install ffmpeg       # macOS; Debian/Ubuntu: apt install ffmpeg
```
`ffmpeg` and `ffprobe` must be on `PATH`. Python 3.11 or newer. The voice model ships inside the
package (checked against a pinned SHA-256 before every use).

## Run

```sh
filmanalyser film.mp4                      # results in ./film.analysis/ (report.html inside)
filmanalyser film.mp4 --out work/film      # choose the folder
filmanalyser film.mp4 --report ~/film.html # put the report somewhere else
filmanalyser film.mp4 -v                   # structured progress events on stderr, one per chunk
filmanalyser --version
```

| Option | Meaning |
|---|---|
| `film` | The film (any file ffmpeg can read; tested with mp4 and mov). |
| `--out DIR` | The folder for the feature store and the report. Default: `<film name>.analysis` in the working folder. |
| `--report FILE` | Where to write the report. Default: `report.html` inside `--out`. It may not be the film itself or a link, and its folder must exist. |
| `--fresh` | Discard the stored results in `--out` and start from the first chunk. |
| `-v`, `--verbose` | Progress events (one JSON line per chunk, with time and peak memory) on stderr; a traceback if something unexpected fails. |
| `--separate-voices` | Opt-in voice separation for stereo or mono films (see below). |
| `--separation-model DIR` | Where the separation model is (default `~/.cache/filmanalyser/htdemucs`, or `FILMANALYSER_SEPARATION_MODEL`). |

## Resuming

The run stores one Parquet file per finished chunk and a manifest. If it stops (Ctrl-C, a crash, a
power cut), run the **same command** again: it resumes at the first unfinished chunk and does not
decode the finished ones. A finished store is read, not recomputed: running again only rewrites the
report. A folder that holds results of another film, other extractor versions or other chunk
settings is refused (exit 5), never mixed; pick another `--out` or pass `--fresh`.

`--fresh` removes only the store's own files (`manifest.json`, `chunk_NNNNNN.parquet`, stale temp
files) from `--out`. Anything else in that folder, and any link, is left alone.

## Exit codes

| Code | Meaning |
|---|---|
| 0 | Done. |
| 1 | An unexpected internal error (run with `-v` for the traceback). |
| 2 | Invalid input or setting: missing or unreadable film, bad report path, missing separation tool. |
| 3 | The film could not be decoded, ffmpeg or ffprobe is missing, or voice separation failed. |
| 4 | A model file is missing or failed its integrity check. |
| 5 | The stored results are damaged or belong to another film or version; the output folder cannot be used. |
| 6 | The analysis could not complete. |
| 130 | Stopped with Ctrl-C. Run the same command to resume. |

Messages go to stderr, in plain words, naming files by basename only.

## What the report holds

Hard cuts and average shot length, the cut-rate curve, brightness, contrast, colourfulness and
warmth, the dominant colours (a strip and the film's top five), the loudness profile, the speech / non-speech-and-tonal / silence shares, the tension curve,
act breaks, pacing plateaus, and flagged moments, each with a timestamp. The page is one file: no
scripts, no network, light and dark themes.

**Read the note at the top of the report.** The act breaks, tension peak, plateaus and flags are
observations from rules that have not been checked against films with known structure. A film
under 13 minutes at the default chunk is "too short to judge", which is not the same as "no break
found". See `docs/LIMITATIONS.md` for every measured limit, including that there is no colour
palette.

## Speech under loud music (stereo films)

A 5.1 film's dialogue is read from its centre channel. For stereo or mono, `--separate-voices` adds
voice separation (Demucs) on chunks with a loud background. Setup once:

```sh
uv tool install demucs==4.1.0   # brings PyTorch; not a project dependency
make separation-model           # the pinned 84 MB model
filmanalyser film.mp4 --separate-voices
```
It is slower (about 8 times real time on an Apple M4 GPU) and reads singing as speech more often.

## Performance and limits

Memory depends on the chunk (60 s), not the film: the budget is under 2 GB for a 3-hour film and a
full run under 45 minutes. Measured results on real films are in `docs/handoff/phase-8.md`.

## Checking the analysis on films you know

`scripts/validate_real_film.py` runs the command on films you name, measures peak memory and run
time of each run, and compares the detected act breaks and the tension peak with times you give it:

```json
{"verified_by": "owner", "tolerance_s": 300, "climax_tolerance_s": 300,
 "films": [{"title": "Film A", "film": "/path/a.mp4", "out": "/path/store-a",
            "act_breaks_s": [1800, 5400], "climax_s": 6300},
           {"title": "Held-out film", "film": "/path/d.mp4", "out": "/path/store-d",
            "held_out": true, "act_breaks_s": [2000, 6000], "climax_s": 7000}]}
```
```sh
uv run python scripts/validate_real_film.py truth.json
```
The times must be your own judgement of the film, not an estimate from anywhere else; the file is
refused unless it says `"verified_by": "owner"`. The output is a Markdown table (with the machine's
chip and memory) and states whether the kill/pivot rule of `ACCEPTANCE.md` fires.
