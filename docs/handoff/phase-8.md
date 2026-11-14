# Phase 8 handoff: CLI, hardening, validation, release

**Status: built on `feat/phase-8-cli-release`, awaiting your approval. PHASE 8 IS NOT COMPLETE.** `make check` exits 0 (1123 passed, coverage 100%, guard self-test 0 failing; raw log at the end). Open, and listed in `EXECUTION_PLAN.md`:

- **P8-1: real-film validation not done.** It needs your act-break and climax times for 3 films you know plus 1 held-out film. P6-1, P6-2, the ACCEPTANCE Validity items, the kill/pivot rule and the held-out-film item all wait on it. I did not use estimated times (DECISIONS #94).
- **P8-2: the release workflow has never run on a tag; nothing is tagged** (neither `v*` nor the schema tag). It waits for your go-ahead.
- **P7-1: no colour palette.** Waiting for your choice (build a palette feature, or strike "palette" from ACCEPTANCE). I did neither.

## What was built

- **Command** (`cli/args.py`, `cli/run.py`, `cli/main.py`): `filmanalyser film.mp4` works with no other option; `--fresh`, `--version`; report path checked before the run; exit codes 0 to 6, 130 and 1; control characters stripped from printed messages (DECISIONS #98). `storage/reset.py` clears only the store's own files.
- **Memory fix** (`extractors/_convolve.py`): found by measurement, see below (DECISIONS #99).
- **Frozen schema and golden clip** (DECISIONS #100).
- **Security audit** (`docs/SECURITY.md`, DECISIONS #101): one finding fixed (terminal escapes in file names).
- **Release** (`release.yml`, Dependabot, `make sbom / changelog / release-assets`, `scripts/release_notes.py`, `docs/RELEASING.md`, DECISIONS #104, #105).
- **Validation tooling** (`scripts/validate_real_film.py`, `validation_judge.py`, DECISIONS #102) and docs (`docs/USAGE.md`, README usage, LIMITATIONS).

## Measured results (Apple M4, 16 GB, ffmpeg 9.0.2, default settings, one run each, `scripts/validate_real_film.py`)

| Film | Length | Peak RAM | Run time | Detected act breaks | Tension peak (>= z 3.0) |
|---|---|---|---|---|---|
| The Odyssey (5.1), **before the fix** | 2:52:35 | **2231 MB (over 2 GB)** | 13:50 | none | 1:51:00 |
| The Odyssey (5.1), after | 2:52:35 | 1505 MB | 12:10 | none | 1:51:00 |
| Moonrise Kingdom | 1:33:38 | 1014 MB | 3:48 | none | none |
| Kill Bill Vol. 1 | 1:50:43 | 1025 MB | 4:10 | none | none |
| Kill Bill Vol. 2 | 2:16:57 | 1022 MB | 4:59 | none | none |
| Licorice Pizza (5.1) | 2:13:24 | 1494 MB | 7:55 | 1:36:00 | none |
| Obsession (2026) | 1:48:53 | 1396 MB | 6:58 | none | none |

Caveats: one run each; other light work ran on the machine during some runs (tests, guard probes), so run times are upper-ish bounds; memory is the command's and its children's peak (`wait4`). The act-break and tension columns are **not validation**: no expected times were given. They repeat DECISIONS #94 (same Licorice Pizza break at 1:36, nothing elsewhere). The Odyssey's report was opened at full length in light and dark and reads correctly (P7-2 closed for that film); the other reports were not opened.

## Review against the Phase 8 section and ACCEPTANCE

| Item | Verdict |
|---|---|
| Tests first: CLI integration (exit codes, bad paths, missing ffmpeg, resume flag), full pipeline on the synthetic film | Done (`test_cli.py`, `test_exit_codes.py`, `test_full_pipeline.py`, `test_hostile_names.py`) |
| `cli/main.py`, `cli/args.py`, thin orchestration, README usage, `docs/USAGE.md` | Done |
| `scripts/validate_real_film.py` | Built and tested; **not run on validation films** (P8-1) |
| Validation on 3 familiar films + 1 held out (RAM, run time, breaks within 5 min, tension peak vs climax, kill/pivot) | **Not done.** RAM and run time measured on six local films: all within budget. Breaks, climax, kill/pivot need your times |
| Security audit: bandit, pip-audit, pins, injection, traversal, XSS | Done |
| `release.yml`, `CHANGELOG.md`, Dependabot | Written and tested statically; **workflow never run** (P8-2) |
| Exit: every ACCEPTANCE box ticked | **No.** 9 of 16 ticked. Unticked: report metrics (palette), the three Validity items, schema tagged, "all items on a held-out film", release tagged |
| Exit: known-limitations list written | Done |
| Open P6-1, P6-2 | Open (P8-1) |
| Open P7-1 | Open (your choice) |
| Open P7-2 | Closed for The Odyssey; re-check on your films in P8-1 |

## Tech debt found, and what was done

| Debt | Resolution |
|---|---|
| 5.1 loudness over the memory budget (2231 MB) | Fixed (DECISIONS #99), regression test and guard mutation |
| Printed file names unfiltered | Fixed, tested |
| The CI definition would have been copied into the release workflow | `ci.yml` made reusable; one definition |
| `cli` could not reach `media` (layer rule) for the default model folder and path check | `pipeline.runner` re-exports them, as before; rule unchanged |
| Argparse's `version` action tripped the string guard | The exact token `version` added to the guard's technical list |
| README described the walking skeleton (one chart) | Rewritten |
| Remaining memory baseline of about 1.1 GB (decode, voice model) | Not resolved: budget met with margin; recorded in #99 |
| Pre-commit hooks check the whole working tree, so partial commits failed | Commits were made with the other changes stashed (each commit passes the hooks) |
| Dependency bounds are lower bounds in the wheel | Decision, not debt (DECISIONS #101) |
| No colour palette; real validation; release run | Cannot be resolved here: P7-1, P8-1, P8-2 |

## Steps taken

1. Read the plan, ACCEPTANCE, handoffs 6 and 7, LIMITATIONS and DECISIONS from #90; branch from `main`.
2. Tests first (CLI, exit codes, hostile names, full pipeline, store reset), then the command.
3. Release pipeline and its tests; validation tooling and its tests.
4. Measured The Odyssey: 2231 MB. Profiled (`tracemalloc`, stubbing extractors), fixed with block convolution, re-measured 1505 MB. Measured five more films.
5. Security audit; fixed the terminal-escape finding.
6. Frozen schema, golden clip, guard probes (all caught).
7. Docs, DECISIONS #98 to #105, ACCEPTANCE, plan status and the P8 rows, CHANGELOG.

## Choices I made that you may want to redirect

1. Default output folder is `<film name>.analysis` in the working folder; resume is the default and `--fresh` restarts.
2. No progress bar: `-v` prints one event per chunk.
3. The report path is refused if it is the film, a link, or in a missing folder.
4. Truth-file attestation (`"verified_by": "owner"`) is required only when times are given.
5. The release notes come from the committed `CHANGELOG.md`; the version section is cut before tagging.
6. The SBOM covers runtime dependencies only. 7. `0BSD` added to the licence allowlist.
8. Frozen schema is a test, not a tag; the tag is part of the release step.

## Build confirmation: raw `make check` output (ANSI stripped)

```text
uv run --locked ruff check .
All checks passed!
uv run --locked ruff format --check .
198 files already formatted
uv run --locked mypy
Success: no issues found in 178 source files
uv run --locked pytest tests/unit tests/architecture tests/integration -m "not real_clip and not slow and not separation"
============================= test session starts ==============================
platform darwin -- Python 3.12.14, pytest-9.2.0, pluggy-1.7.0
rootdir: /Users/sunil/Downloads/FilmAnalyser
configfile: pyproject.toml
plugins: platformdirs-4.14.5, hypothesis-6.170.15, cov-7.1.0
collected 1130 items / 7 deselected / 1123 selected

tests/unit/test_act_breaks.py .......................................... [  3%]
................................................................         [  9%]
tests/unit/test_analysis_golden.py ..                                    [  9%]
tests/unit/test_audio_argv.py .........................                  [ 11%]
tests/unit/test_audio_chunk.py ...............                           [ 13%]
tests/unit/test_charts.py .........                                      [ 13%]
tests/unit/test_chunk.py ............................                    [ 16%]
tests/unit/test_chunker.py ..............                                [ 17%]
tests/unit/test_cli_args.py .......                                      [ 18%]
tests/unit/test_color.py .........                                       [ 19%]
tests/unit/test_config.py ................                               [ 20%]
tests/unit/test_convolve.py .......                                      [ 21%]
tests/unit/test_dialogue_signal.py ...                                   [ 21%]
tests/unit/test_display.py ...                                           [ 21%]
tests/unit/test_ebu_reference.py .............                           [ 22%]
tests/unit/test_errors.py .........                                      [ 23%]
tests/unit/test_evaluate_labels.py ................                      [ 25%]
tests/unit/test_events.py ...............                                [ 26%]
tests/unit/test_feature_store.py ...........................             [ 28%]
tests/unit/test_ffmpeg_stream.py ..........                              [ 29%]
tests/unit/test_files.py .........................                       [ 31%]
tests/unit/test_flags.py .............                                   [ 33%]
tests/unit/test_gradual.py ................                              [ 34%]
tests/unit/test_letterbox.py .....                                       [ 34%]
tests/unit/test_loudness.py ...........................                  [ 37%]
tests/unit/test_manifest.py .............................                [ 39%]
tests/unit/test_model_integrity.py .................                     [ 41%]
tests/unit/test_pacing.py .........                                      [ 42%]
tests/unit/test_paths.py ................                                [ 43%]
tests/unit/test_probe.py .................                               [ 45%]
tests/unit/test_registry.py .....................                        [ 47%]
tests/unit/test_release_notes.py ............                            [ 48%]
tests/unit/test_renderer.py ..................                           [ 49%]
tests/unit/test_report_keys.py ....................................      [ 52%]
tests/unit/test_resources.py ..........................                  [ 55%]
tests/unit/test_runner.py .........                                      [ 56%]
tests/unit/test_schema.py ..............................                 [ 58%]
tests/unit/test_schema_frozen.py ..                                      [ 58%]
tests/unit/test_separation.py ....................                       [ 60%]
tests/unit/test_shot_cuts.py ..........                                  [ 61%]
tests/unit/test_speech_music.py .............                            [ 62%]
tests/unit/test_store_reset.py ........                                  [ 63%]
tests/unit/test_tension.py ............................................. [ 67%]
..                                                                       [ 67%]
tests/unit/test_timeline.py ........................                     [ 69%]
tests/unit/test_validate_real_film.py ........                           [ 70%]
tests/unit/test_validation_judge.py ...............                      [ 71%]
tests/unit/test_viewmodel.py ...........................                 [ 74%]
tests/architecture/test_analysis_purity.py .........                     [ 75%]
tests/architecture/test_atomic_writes.py ....                            [ 75%]
tests/architecture/test_ci_workflow.py ..........                        [ 76%]
tests/architecture/test_color_contrast.py ..........................     [ 78%]
tests/architecture/test_error_keys.py ....                               [ 78%]
tests/architecture/test_file_size.py ......                              [ 79%]
tests/architecture/test_frozen_dataclasses.py ....                       [ 79%]
tests/architecture/test_function_limits.py ...                           [ 80%]
tests/architecture/test_layer_imports.py ..............                  [ 81%]
tests/architecture/test_model_fetch.py .........                         [ 82%]
tests/architecture/test_model_loading.py ..                              [ 82%]
tests/architecture/test_nightly_workflow.py ........                     [ 83%]
tests/architecture/test_no_hardcoded_colors.py ........                  [ 83%]
tests/architecture/test_no_hardcoded_strings.py ...........              [ 84%]
tests/architecture/test_no_skips.py ...                                  [ 85%]
tests/architecture/test_release_workflow.py ........                     [ 85%]
tests/architecture/test_report_templates.py .......                      [ 86%]
tests/architecture/test_security_patterns.py ..............              [ 87%]
tests/architecture/test_subprocess_argv.py .....                         [ 88%]
tests/integration/test_analysis_pipeline.py .....                        [ 88%]
tests/integration/test_audio_decode.py ..........                        [ 89%]
tests/integration/test_audio_offset.py .....                             [ 89%]
tests/integration/test_av_pipeline.py .....                              [ 90%]
tests/integration/test_cli.py ..........                                 [ 91%]
tests/integration/test_decode_stream.py ................                 [ 92%]
tests/integration/test_determinism.py ...                                [ 92%]
tests/integration/test_evaluate_labels.py ...                            [ 93%]
tests/integration/test_exit_codes.py ...............                     [ 94%]
tests/integration/test_extract_budget.py .                               [ 94%]
tests/integration/test_ffmpeg_version.py .                               [ 94%]
tests/integration/test_full_pipeline.py .....                            [ 95%]
tests/integration/test_golden_clip.py ..                                 [ 95%]
tests/integration/test_gradual_detection.py .                            [ 95%]
tests/integration/test_hires_decode.py ..                                [ 95%]
tests/integration/test_hostile_names.py ......                           [ 96%]
tests/integration/test_memory_flat.py ...                                [ 96%]
tests/integration/test_report_render.py ........                         [ 97%]
tests/integration/test_resume.py ......                                  [ 97%]
tests/integration/test_resume_grid.py ..                                 [ 97%]
tests/integration/test_separation_pipeline.py ........                   [ 98%]
tests/integration/test_vad.py ..........                                 [ 99%]
tests/integration/test_video_pipeline.py ......                          [ 99%]
tests/integration/test_wheel_resources.py .                              [100%]

================================ tests coverage ================================
______________ coverage: platform darwin, python 3.12.14-final-0 _______________

Name    Stmts   Miss Branch BrPart  Cover   Missing
---------------------------------------------------
TOTAL    2590      0    470      0   100%

58 files skipped due to complete coverage.
Required test coverage of 90% reached. Total coverage: 100.00%
================ 1123 passed, 7 deselected in 77.21s (0:01:17) =================
mkdir -p .cache
uv export --locked --no-emit-project --format requirements-txt -o .cache/audit-requirements.txt >/dev/null
Resolved 94 packages in 2ms
uv run --locked pip-audit --require-hashes --disable-pip -r .cache/audit-requirements.txt
No known vulnerabilities found
uv run --locked pip-licenses --allow-only="MIT License;MIT;BSD License;3-Clause BSD License;BSD-2-Clause;BSD-3-Clause;Apache Software License;Apache-2.0;Apache-2.0 OR BSD-2-Clause;Python Software Foundation License;PSF-2.0;ISC License (ISCL);MPL-2.0;Mozilla Public License 2.0 (MPL 2.0);The Unlicense (Unlicense);0BSD;BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0" --format=plain >/dev/null
gitleaks dir . --no-banner --redact -v
10:10PM INF scanned ~8084233 bytes (8.08 MB) in 488ms
10:10PM INF no leaks found
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
  ok   a short film reported as judged (too short read as nothing found): caught
  ok   template runs a script: caught
  ok   template links an external address: caught
  ok   template has an inline style: caught
  ok   template has an event handler: caught
  ok   template uses an undefined colour token: caught
  ok   template imports a stylesheet: caught
  ok   view model part reads a file: caught
  ok   view imports analysis: caught
  ok   plain English in the report code: caught
  ok   chart geometry reads a file: caught
  ok   a zone too short to judge reads as no break: caught
  ok   the sound statement always says sound was used: caught
  ok   the unvalidated notice is left off the page: caught
  ok   the page escapes nothing: caught
  ok   a flag is shown without its timestamp: caught
  ok   the report may overwrite the film: caught
  ok   an interrupt exits as an internal error: caught
  ok   an unexpected failure prints its traceback without -v: caught
  ok   a file name's terminal escape is printed as it is: caught
  ok   --fresh deletes files that are not the store's: caught
  ok   --fresh follows a symlink: caught
  ok   release builds before the suite passed: caught
  ok   release workflow can write in every job: caught
  ok   release published without a checksum check: caught
  ok   release notes accept a tag that is not the version: caught
  ok   an extractor version is bumped without updating the frozen schema: caught
  ok   the luma weights change without updating the golden clip: caught
  ok   loudness transforms a whole window at once (5.1 memory peak): caught
  ok   template literal text: caught
  ok   template |safe output: caught
  ok   committed secret (gitleaks): caught
  ok   vulnerable pin (pip-audit): caught
  ok   disallowed licence: caught
guard self-test: 0 failing guard(s)
```
