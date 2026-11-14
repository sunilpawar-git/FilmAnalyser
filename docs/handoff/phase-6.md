# Phase 6 handoff: Timeline analysis (the stitching)

**Status: built on `feat/phase-6-analysis`, awaiting your approval before merge.** `make check` exits 0 on this tree (911 passed, 7 deselected; log at the end). **Three items are open** and are listed as P6-1 to P6-3 in `EXECUTION_PLAN.md`: the act-break, tension, pacing and flag rules are tested on constructed timelines only, and no real film produced an act break.

## What was built

- **`analysis/timeline.py`**: the store's columns as aligned, read-only series (`build_timeline`), plus `zscores` and `smooth`. Missing values are NaN: loudness at the -70 LUFS floor is missing, not a value. A last chunk under half the usual length is dropped from the series, while the film still ends at its real end. `AnalysisError` (`error.analysis.bad_timeline`) for a missing or misaligned column.
- **`analysis/act_breaks.py`**: your specification, as written (DECISIONS #90): state vector of z-scored features smoothed over 3 chunks; boundary score = distance between the means of the 5 chunks before and after, over the square root of the features compared; local maxima above `ACT_MIN_SCORE`, merged within 10 chunks; at most one break in each of the two zones; no break forced; the 25% / 75% prior only as a tie-break within 5%. Result: boundary, container-clock time, score, the two features that moved most, acts as spans, `empty_zones`, `features_used`, `audio_used`, `scored`.
- **`analysis/pacing.py`, `tension.py`, `flags.py`**: the plan names them and gives no formulas, so these are my definitions (DECISIONS #91): plateaus (runs of 5+ chunks whose z-scored cut rate stays within 0.5), tension (mean of cut-rate and loudness z-scores, peak at 3.0 standard deviations or more), five flags (`fast_cutting`, `loud`, `quiet`, `clipping`, `long_take`).
- **Thresholds**: 25 new names in `core/config.py` (all `ACT_*`, `TENSION_*`, `PACING_*`, `FLAG_*`, `TIMELINE_*`, `Z_EPSILON`, `SECONDS_PER_MINUTE`); feature names in `core/features.py`. `tests/architecture/test_analysis_purity.py` fails on any number in `analysis/` other than 0, 1 and 2.
- **Extractors unchanged.** No extractor was touched, so no version was bumped.
- **Scripts**: `scripts/timeline_report.py STORE` (verifies the store's hashes, prints the four analyses as observations), `scripts/calibrate_analysis.py` (reproduces the threshold numbers), `scripts/guard_probes_phase6.py`.
- **Fixture**: `make_av_clip(..., flat=True)` writes a still grey picture (the default ramp repeats every 8 s and looks like cuts to the detector).

## Review against the Phase 6 section (checked against the code, not memory)

| Plan bullet | Where it is | Verdict |
|---|---|---|
| Tests first: synthetic timelines with known change points | `tests/fixtures/timelines.py` (`block_film`, `noise_film`, `golden_film`); `test_act_breaks.py` | Done. The tests were written before the modules; the first run failed on thresholds and on four of my own test designs, which were then corrected (below) |
| ... a known peak | `test_tension.py` (peak within one chunk of the planted bump, with and without audio, with a silent stretch) | Done |
| ... known flat stretches | `test_pacing.py` (exact span of a planted plateau, two plateaus, too short, none in an alternating film, a flat film) | Done |
| ... assert act breaks, tension peak, pacing plateaus, flagged timestamps | the four unit test files; `tests/golden/analysis_tent_film.json` pins all four on one film; `test_analysis_pipeline.py` runs them on features the real pipeline stored | Done |
| Deliver `pacing.py`, `tension.py`, `act_breaks.py`, `flags.py` | `src/filmanalyser/analysis/` (and `timeline.py`, which the plan's file table also lists) | Done |
| Every threshold lives in `core/config.py` | the purity test fails on a stray number; guard probe plants one | Done |
| Exit: green build | log below | Done |
| Exit: pure functions, no I/O, no report imports (architecture test) | `test_layer_imports.py` (existing: analysis may import only core, and no I/O modules) plus the new `test_analysis_purity.py` (no randomness or clock, no `open`/`print`, no stray numbers, the five modules exist, nothing from report); 6 guard probes | Done |
| Use the stored features as they are | no extractor changed | Done |
| Act-break specification, items 1 to 5 | DECISIONS #90 lists each and the choices where it was silent; every test case you listed exists: three blocks, one step, flat, noise (40 seeds, with and without audio), outside a zone (6 positions), below the threshold, two close steps (both orders), shorter than 2W (0, 1, 5, 9 chunks), no audio, silent stretch, same input twice | Done, with no deviation from the specification |
| Run on the real films and report plainly | below; `docs/LIMITATIONS.md` section "Timeline analysis" | Done. Result: no act break on any film |
| Record that there is no ground truth, and which thresholds were synthetic only | `docs/LIMITATIONS.md`, DECISIONS #92 | Done |

## Real-film observations (as measured, not as acts)

Run with `scripts/timeline_report.py` on stores made by the CLI with the default 60 s chunks.

| Film | Chunks | Boundaries scored | Act breaks | Tension peak | Pacing plateaus | Flags |
|---|---|---|---|---|---|---|
| The Odyssey, 5.1 (2 h 52 min) | 173 | 164 | none (best in zone 1: 1.15 at 0:31, 18%; zone 2: 1.27 at 2:21, 82%; threshold 1.5) | 1:51 (z 3.49) | 4 (0:17 to 0:24; 2:13 to 2:18; 2:28 to 2:33; 2:46 to the end at 0 cuts per minute) | clipping 8, fast_cutting 1 (1:50 to 1:53), long_take 1 (2:46 to the end), loud 1 (1:51), quiet 1 (0:32) |
| Tears of Steel, stereo (12 min) | 12 | 3 | none | none | 0 | clipping 2 |
| Tears of Steel, 5.1 (12 min) | 12 | 3 | none | none | 0 | fast_cutting 1 |
| Stitched film (80 s, no audio) | 2 | 0 | none (too short) | none | 0 | none |

Only The Odyssey is long enough for the specified analysis. As an exploration, Tears of Steel was re-run with 10 s chunks (73 chunks, window 50 s): still no break (best inside a zone: 1.05 and 0.84); two plateaus (8:50 to 9:40; 10:30 to 11:40, which has no cuts); the strongest candidate overall (1.27, 1:00) lies outside both zones. These are the numbers; they are not claimed to be right or wrong acts. The threshold was not lowered to make a break appear.

## 1. Tech debt incurred and found, and 2. exact steps taken to resolve each item

| # | Debt (found during the phase) | Resolution |
|---|---|---|
| 1 | Stale plan text: the Phase 5 section and the sentence under the pending table still said Phase 5 awaited approval and P5-1 to P5-5 were open | Both rewritten (`EXECUTION_PLAN.md`): Phases 1 to 5 complete and merged, P5 items closed |
| 2 | The first `ACT_MIN_SCORE` (1.0) was a guess and noise crossed it (video-only noise reached 1.36) | Measured instead (`scripts/calibrate_analysis.py`, 2,400 noise films); set to 1.5, DECISIONS #92. `TENSION_MIN_PEAK_Z` 1.0 was also below noise (2.75); set to 3.0 |
| 3 | Five of my first test designs were wrong, not the code: steps too weak after z-scoring, a plateau band wider than the gap I planted, tension tests with one constant component, a 24-chunk integration film shorter than the merge gap, a ramp picture that repeats every 8 s and reads as cuts | Each test redesigned and the reason recorded in its docstring or comment; the ramp problem fixed with a `flat` option in `make_synthetic.py` |
| 4 | A dead branch (`film_state` for a timeline with no state names) and an unreachable flag branch | The dead branch removed; flag rules made a table, so one loop covers every rule (`flags.py`) |
| 5 | Two thresholds-as-literals (`60.0` seconds per minute, `-1.0` in the "moved most" sort) | `SECONDS_PER_MINUTE` moved to config; the sort rewritten with infinity, no literal. The purity test now forbids the pattern |
| 6 | The calibration and real-film runs were throw-away scripts in the scratchpad, not reproducible | Rewritten as `scripts/calibrate_analysis.py` and `scripts/timeline_report.py` (typed, linted, bandit-clean, hash-verifying) |
| 7 | A test fixture docstring was over the line length after my edit, and `make_av_clip` gained a keyword | Wrapped; the existing callers are unchanged (default `flat=False`) |
| 8 | The Phase 6 rules had no guard probes, and the first guard self-test run found a real gap: removing the merge gap (`abs(t - other) >= 0`) left every test green, because two close candidates in one zone are separated by the zone choice anyway | Added the case where merging is observable: a stronger change just outside a zone absorbs a weaker in-zone candidate (`test_a_stronger_change_just_outside_a_zone_absorbs_a_close_candidate_inside_it`, with a control showing the in-zone candidate is a break on its own). The mutation is now caught. Guard probes | `scripts/guard_probes_phase6.py`: 6 planted violations (randomness, clock, print, a threshold in code, a report import, `os`) and 4 mutations (loudness floor read as a value, zone widened, threshold ignored, close candidates not merged), registered in `guard_selftest.py` |

## Decisions that remain as known weaknesses (recorded, not silent)

- A plateau's band and a flag's z-limit use the film's own standard deviation, which a few huge bursts inflate (DECISIONS #91). A robust spread was not adopted without real footage to judge it on.
- A constant tension component dilutes the mean instead of being dropped (DECISIONS #91).
- A change in a minority of features, and a film that climbs in equal stages, score below the threshold by construction (DECISIONS #90, tested, `docs/LIMITATIONS.md`).

## Unresolved (fail loudly; consolidated in `EXECUTION_PLAN.md`)

- **P6-1** Act breaks are unvalidated on real films; `ACT_MIN_SCORE` is calibrated on synthetic data only; The Odyssey gives none.
- **P6-2** Tension peak, plateaus and flags are unvalidated against a real climax or any human judgement.
- **P6-3** Films under 10 minutes cannot be scored at the default chunk size; the choice is for Phase 8.

## Choices I made that you may want to redirect

1. The picture features are brightness, contrast, colourfulness, warmth; the letterbox share is excluded (an aspect-ratio change would swamp the rest).
2. The last chunk is dropped from the series when under half the usual length.
3. Zones use time fraction (boundary chunk start over film end), inclusive bounds.
4. `ACT_MIN_SCORE` 1.5 and `TENSION_MIN_PEAK_Z` 3.0, from noise only.
5. Pacing, tension and flags use my own definitions (DECISIONS #91) because the plan had none.
6. The integration test lowers the act threshold to 0.8: a film where only the sound changes dilutes the score by the still picture's features, and that test is about the path from store to answer.
7. `scripts/timeline_report.py` and `calibrate_analysis.py` are new files outside the plan's list.

## Build confirmation: raw `make check` output (ANSI stripped)

```text
uv run --locked ruff check .
All checks passed!
uv run --locked ruff format --check .
163 files already formatted
uv run --locked mypy
Success: no issues found in 148 source files
uv run --locked pytest tests/unit tests/architecture tests/integration -m "not real_clip and not slow and not separation"
============================= test session starts ==============================
platform darwin -- Python 3.12.14, pytest-9.2.0, pluggy-1.7.0
rootdir: /Users/sunil/Downloads/FilmAnalyser
configfile: pyproject.toml
plugins: platformdirs-4.14.5, hypothesis-6.170.15, cov-7.1.0
collected 918 items / 7 deselected / 911 selected


================================ tests coverage ================================
______________ coverage: platform darwin, python 3.12.14-final-0 _______________

Name    Stmts   Miss Branch BrPart  Cover   Missing
---------------------------------------------------
TOTAL    2227      0    420      0   100%

50 files skipped due to complete coverage.
Required test coverage of 90% reached. Total coverage: 100.00%
================= 911 passed, 7 deselected in 62.13s (0:01:02) =================
mkdir -p .cache
uv export --locked --no-emit-project --format requirements-txt -o .cache/audit-requirements.txt >/dev/null
Resolved 73 packages in 3ms
uv run --locked pip-audit --require-hashes --disable-pip -r .cache/audit-requirements.txt
No known vulnerabilities found
uv run --locked pip-licenses --allow-only="MIT License;MIT;BSD License;3-Clause BSD License;BSD-2-Clause;BSD-3-Clause;Apache Software License;Apache-2.0;Apache-2.0 OR BSD-2-Clause;Python Software Foundation License;PSF-2.0;ISC License (ISCL);MPL-2.0;Mozilla Public License 2.0 (MPL 2.0);The Unlicense (Unlicense);BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0" --format=plain >/dev/null
gitleaks dir . --no-banner --redact -v
5:38PM INF scanned ~7153358 bytes (7.15 MB) in 424ms
5:38PM INF no leaks found
uv run --locked bandit -q -r src scripts -c pyproject.toml
uv build --wheel --out-dir dist
Building wheel...
Successfully built dist/filmanalyser-0.1.0-py3-none-any.whl
uv run --locked python scripts/guard_selftest.py
  ok   file over 300 lines: caught
  ok   core imports report: caught
  ok   pure core imports os: caught
  ok   view imports analysis: caught
  ok   literal string in cli: caught
  ok   hex colour in report: caught
  ok   mutable dataclass: caught
  ok   function over 40 lines: caught
  ok   direct file write in storage (not atomic): caught
  ok   inline ffmpeg argv (option injection): caught
  ok   unknown error message key: caught
  ok   shell=True in media: caught
  ok   pickle import: caught
  ok   eval call: caught
  ok   network import: caught
  ok   subprocess outside media: caught
  ok   security suppression comment: caught
  ok   bandit: shell=True: caught
  ok   complexity over 10: caught
  ok   more than 5 arguments: caught
  ok   untyped function (mypy --strict): caught
  ok   coverage below gate: caught
  ok   ffprobe path no longer after `--`: caught
  ok   ffmpeg input loses file: protocol lock: caught
  ok   path validation accepts directories: caught
  ok   path validation accepts NUL bytes: caught
  ok   resume no longer seeks (re-decodes finished chunks): caught
  ok   atomic write loses its rename: caught
  ok   store accepts a symlink in place of a file: caught
  ok   store accepts a path with directories (traversal): caught
  ok   file reads are no longer size-bounded: caught
  ok   feature version mismatch is accepted (mixed outputs): caught
  ok   chunk hash is no longer verified: caught
  ok   store accepts out-of-order or repeated chunks (not append-only): caught
  ok   test that skips (no skips rule): caught
  ok   extractor imports media (layer rule): caught
  ok   plain English text in the CLI (not from strings.toml): caught
  ok   resume grid re-anchored to the first decoded frame (P3-1): caught
  ok   boundary cut dropped (overlap not compared): caught
  ok   report not autoescaped: caught
  ok   report allows external requests (CSP removed): caught
  ok   letterbox bars from one dark frame (median removed): caught
  ok   nightly workflow gets write access: caught
  ok   separation may download its model (--repo removed): caught
  ok   separation output made random (shifts removed): caught
  ok   separation model used without its check: caught
  ok   separation model hash not compared: caught
  ok   5.1 film separated instead of using its centre channel: caught
  ok   analysis uses randomness: caught
  ok   analysis reads the clock: caught
  ok   analysis prints: caught
  ok   analysis hides a threshold in code: caught
  ok   analysis imports report: caught
  ok   analysis imports os: caught
  ok   loudness floor read as a value, not as missing: caught
  ok   first zone widened to the film's start (changes outside the zone reported): caught
  ok   break threshold ignored: caught
  ok   close candidates not merged: caught
  ok   template literal text: caught
  ok   template |safe output: caught
  ok   committed secret (gitleaks): caught
  ok   vulnerable pin (pip-audit): caught
  ok   disallowed licence: caught
guard self-test: 0 failing guard(s)
```
