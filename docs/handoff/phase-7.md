# Phase 7 handoff: Report (MVVM view layer)

**Status: built on `feat/phase-7-report`, awaiting your approval before merge.** `make check` exits 0 on this tree (1023 passed, 7 deselected, coverage 100%; raw log at the end). **Two items are open**, listed as P7-1 and P7-2 in `EXECUTION_PLAN.md`: the report has no colour palette (ACCEPTANCE lists one), and it has not been viewed on a real feature film. P6-1 and P6-2 (act breaks, tension, plateaus, flags unvalidated) remain open from Phase 6; the report labels those results as unvalidated instead of waiting.

## What was built

- **`report/viewmodel.py`**: runs the Phase 6 analysis on the store's columns and returns frozen, display-ready values: overview, acts (breaks, zones, spans, whether sound was used), tension, pacing, flags, charts. Pure and locale-neutral: values are text with a point and a colon, words are keys. `viewmodel_charts.py` chooses each chart's series, scale, markers and bands.
- **`report/charts.py`**: values to SVG coordinates (one decimal, deterministic); a gap in the data splits a line; markers (act breaks, tension peak) and shaded bands (plateaus) sit on the film clock.
- **`report/display.py`**, **`report/resources/keys.py`**: number and time text, and the strings.toml key and CSS class names, each defined once.
- **`report/renderer.py`** and **templates** (`report.html`, `partials/*.html`): Jinja2, autoescape on, StrictUndefined; loops and `t(key, ...)` lookups only; charts drawn as inline SVG; strict CSP (`default-src 'none'; style-src 'unsafe-inline'`); light and dark tokens.
- **Honesty rules** (DECISIONS #96): a note before any finding that cannot be switched off (unvalidated, P6-1 and P6-2, calibrated on synthetic data only); a zone in `unscored_zones` reads "too short to judge (needs M:SS)", a judged empty zone reads "no break found"; the act section states whether sound was used.
- **Tests, written first**: `test_viewmodel.py`, `test_charts.py`, `test_display.py`, `test_renderer.py`, `test_report_keys.py`, `architecture/test_report_templates.py`, `integration/test_report_render.py`. The existing CLI and video-pipeline tests were updated to the new view (`view.overview.total_cuts`).
- **Guards**: the layering test now treats `viewmodel_*`, `charts` and `display` as pure and lets only `viewmodel*` import analysis; the string guard allows f-string format specs; `scripts/guard_probes_phase7.py` adds 9 planted violations and 6 mutations, all caught. A Phase 4 probe was renamed to the new CSP test.
- **CLI**: one line changed (it reads the cut total from the new view). The full CLI is Phase 8.

## Review against the Phase 7 section and ACCEPTANCE

| Item | Where | Verdict |
|---|---|---|
| Tests first: ViewModel unit tests, numbers in, structure out, locale-neutral | `test_viewmodel.py`, `test_display.py` (ASCII-only text test) | Done |
| Renderer: HTML escaping | `test_renderer.py`, `test_report_render.py` (`a&b.mp4` becomes `a&amp;b.mp4`) | Done |
| Renderer: no inline literals | `test_no_hardcoded_strings.py` scans templates and code; the rendered page has no unresolved placeholder | Done |
| Renderer: only `var(--token)` colours, light and dark both defined | renderer test (every `var()` names a defined token, no colour literal outside `:root`, both palettes present, dark media query); `test_report_templates.py` | Done |
| Renderer: no external requests, strict CSP meta tag | renderer, integration and template tests; mutation probe on the CSP | Done |
| Deliver viewmodel, renderer (Jinja2, autoescape), templates, inline SVG, no JS, no network | files above | Done |
| Exit: green build; the report for the synthetic clip passes the architecture tests | the architecture scans cover the templates and code; `test_report_render.py` applies the same page checks to a report built from a pipeline-made clip | Done (the scans run on the templates, not on a rendered page; the integration test covers the page) |
| Consumes ActBreaks, Tension, Pacing, flags | `viewmodel.py` | Done |
| `unscored_zones` reads "too short to judge (needs MM:SS)", never "no break" | tests with 12 chunks and with a 6 s clip ("needs 0:13"); mutation probe | Done |
| Judged empty zone reads "no break found" | tests | Done |
| Audio use stated | tests, mutation probe | Done |
| Observations with a visible unvalidated note | tests, mutation probe | Done |
| ACCEPTANCE: shot cuts, average shot length | overview | Done |
| ACCEPTANCE: cut-rate curve | chart | Done |
| ACCEPTANCE: colour palette and brightness | brightness, contrast, colourfulness, warmth curves | **Gap: no palette (P7-1, DECISIONS #97)** |
| ACCEPTANCE: loudness profile | chart (absent for a film without sound) | Done |
| ACCEPTANCE: speech / music / silence ratio | chart; the tonal share is labelled "non-speech and tonal" (DECISIONS #75) | Done |
| ACCEPTANCE: tension curve, act breaks | chart, section | Done |
| ACCEPTANCE: flagged timestamps, every flag has one | table; a test over every row | Done |
| ACCEPTANCE validity items (breaks within 5 min, tension near the climax) | not Phase 7 | Open: P6-1, P6-2 |

Not measured: the report on a real feature film (P7-2). I viewed a constructed 100-chunk film in a browser, in light and dark; I did not view a real one.

## Tech debt found, and what was done

| Debt | Resolution |
|---|---|
| `scripts/timeline_report.py` had its own clock formatter, a duplicate of the report's | It imports `report.display.clock_text`; its times print as M:SS or H:MM:SS |
| Chart marker labels sat on top of the lines; marker legend entries had no symbol | Halo behind the labels; legend swatches for markers and bands |
| Keys built by string concatenation in several places | One module (`resources/keys.py`) and a test that every key resolves |
| Flag decimals keyed by string | Keyed by the `FlagKind` enum |
| No colour palette | Cannot be resolved here: it needs a new extractor feature and re-extraction. DECISIONS #97, P7-1 |
| Real-film view | Cannot be resolved here without a real store. P7-2 |

## Steps taken

1. Read the plan, the Phase 6 handoff, the limitations and DECISIONS from #90; branch `feat/phase-7-report` from `main`.
2. Wrote the failing tests (view model, charts, renderer, then the integration test).
3. Implemented display, charts, view model, templates, renderer and resources; fixed what the architecture tests found (literal text in code and templates, the pure-module rule, function length, argument count).
4. Added the template guard and the Phase 7 probes; ran `make guards`.
5. Rendered the constructed film, looked at it in a browser (light and dark), fixed label and legend problems.
6. Reviewed against the plan and ACCEPTANCE (above); wrote DECISIONS #95 to #97, the limitations section, the plan status and the P7 rows.

## Choices I made that you may want to redirect

1. The unvalidated note is always on, not switchable, and names P6-1 and P6-2 in its text, as you asked.
2. Times are M:SS, or H:MM:SS from one hour on.
3. The picture chart draws four lines on one automatic scale; warmth is small next to brightness.
4. The mix chart is a fixed 0 to 1 scale; the cut-rate chart starts at 0.
5. `viewmodel_charts.py` is a second view-model module so no file passes 300 lines.
6. The CLI was not extended (Phase 8).

## Build confirmation: raw `make check` output (ANSI stripped)

```text
uv run --locked ruff check .
All checks passed!
uv run --locked ruff format --check .
173 files already formatted
uv run --locked mypy
Success: no issues found in 158 source files
uv run --locked pytest tests/unit tests/architecture tests/integration -m "not real_clip and not slow and not separation"
============================= test session starts ==============================
platform darwin -- Python 3.12.14, pytest-9.2.0, pluggy-1.7.0
rootdir: /Users/sunil/Downloads/FilmAnalyser
configfile: pyproject.toml
plugins: platformdirs-4.14.5, hypothesis-6.170.15, cov-7.1.0
collected 1030 items / 7 deselected / 1023 selected

tests/unit/test_act_breaks.py .......................................... [  4%]
................................................................         [ 10%]
tests/unit/test_analysis_golden.py ..                                    [ 10%]
tests/unit/test_audio_argv.py .........................                  [ 13%]
tests/unit/test_audio_chunk.py ...............                           [ 14%]
tests/unit/test_charts.py .........                                      [ 15%]
tests/unit/test_chunk.py ............................                    [ 18%]
tests/unit/test_chunker.py ..............                                [ 19%]
tests/unit/test_color.py .........                                       [ 20%]
tests/unit/test_config.py ................                               [ 21%]
tests/unit/test_dialogue_signal.py ...                                   [ 22%]
tests/unit/test_display.py ...                                           [ 22%]
tests/unit/test_ebu_reference.py .............                           [ 23%]
tests/unit/test_errors.py .........                                      [ 24%]
tests/unit/test_evaluate_labels.py ................                      [ 26%]
tests/unit/test_events.py ...............                                [ 27%]
tests/unit/test_feature_store.py ...........................             [ 30%]
tests/unit/test_ffmpeg_stream.py ..........                              [ 31%]
tests/unit/test_files.py .........................                       [ 33%]
tests/unit/test_flags.py .............                                   [ 34%]
tests/unit/test_gradual.py ................                              [ 36%]
tests/unit/test_letterbox.py .....                                       [ 37%]
tests/unit/test_loudness.py ...........................                  [ 39%]
tests/unit/test_manifest.py .............................                [ 42%]
tests/unit/test_model_integrity.py .................                     [ 44%]
tests/unit/test_pacing.py .........                                      [ 45%]
tests/unit/test_paths.py ................                                [ 46%]
tests/unit/test_probe.py .................                               [ 48%]
tests/unit/test_registry.py .....................                        [ 50%]
tests/unit/test_renderer.py ..................                           [ 52%]
tests/unit/test_report_keys.py ....................................      [ 55%]
tests/unit/test_resources.py ..........................                  [ 58%]
tests/unit/test_runner.py .........                                      [ 59%]
tests/unit/test_schema.py ..............................                 [ 61%]
tests/unit/test_separation.py ....................                       [ 63%]
tests/unit/test_shot_cuts.py ..........                                  [ 64%]
tests/unit/test_speech_music.py .............                            [ 66%]
tests/unit/test_tension.py ............................................. [ 70%]
..                                                                       [ 70%]
tests/unit/test_timeline.py ........................                     [ 73%]
tests/unit/test_viewmodel.py ...........................                 [ 75%]
tests/architecture/test_analysis_purity.py .........                     [ 76%]
tests/architecture/test_atomic_writes.py ....                            [ 77%]
tests/architecture/test_ci_workflow.py ..........                        [ 78%]
tests/architecture/test_color_contrast.py ..........................     [ 80%]
tests/architecture/test_error_keys.py ....                               [ 80%]
tests/architecture/test_file_size.py ......                              [ 81%]
tests/architecture/test_frozen_dataclasses.py ....                       [ 81%]
tests/architecture/test_function_limits.py ...                           [ 82%]
tests/architecture/test_layer_imports.py ..............                  [ 83%]
tests/architecture/test_model_fetch.py .........                         [ 84%]
tests/architecture/test_model_loading.py ..                              [ 84%]
tests/architecture/test_nightly_workflow.py ........                     [ 85%]
tests/architecture/test_no_hardcoded_colors.py ........                  [ 86%]
tests/architecture/test_no_hardcoded_strings.py ...........              [ 87%]
tests/architecture/test_no_skips.py ...                                  [ 87%]
tests/architecture/test_report_templates.py .......                      [ 88%]
tests/architecture/test_security_patterns.py ..............              [ 89%]
tests/architecture/test_subprocess_argv.py .....                         [ 90%]
tests/integration/test_analysis_pipeline.py .....                        [ 90%]
tests/integration/test_audio_decode.py ..........                        [ 91%]
tests/integration/test_audio_offset.py .....                             [ 92%]
tests/integration/test_av_pipeline.py .....                              [ 92%]
tests/integration/test_cli.py .....                                      [ 93%]
tests/integration/test_decode_stream.py ................                 [ 94%]
tests/integration/test_determinism.py ...                                [ 94%]
tests/integration/test_evaluate_labels.py ...                            [ 95%]
tests/integration/test_extract_budget.py .                               [ 95%]
tests/integration/test_ffmpeg_version.py .                               [ 95%]
tests/integration/test_gradual_detection.py .                            [ 95%]
tests/integration/test_hires_decode.py ..                                [ 95%]
tests/integration/test_memory_flat.py ...                                [ 95%]
tests/integration/test_report_render.py ........                         [ 96%]
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
TOTAL    2500      0    448      0   100%

54 files skipped due to complete coverage.
Required test coverage of 90% reached. Total coverage: 100.00%
================ 1023 passed, 7 deselected in 68.99s (0:01:08) =================
mkdir -p .cache
uv export --locked --no-emit-project --format requirements-txt -o .cache/audit-requirements.txt >/dev/null
Resolved 73 packages in 3ms
uv run --locked pip-audit --require-hashes --disable-pip -r .cache/audit-requirements.txt
No known vulnerabilities found
uv run --locked pip-licenses --allow-only="MIT License;MIT;BSD License;3-Clause BSD License;BSD-2-Clause;BSD-3-Clause;Apache Software License;Apache-2.0;Apache-2.0 OR BSD-2-Clause;Python Software Foundation License;PSF-2.0;ISC License (ISCL);MPL-2.0;Mozilla Public License 2.0 (MPL 2.0);The Unlicense (Unlicense);BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0" --format=plain >/dev/null
gitleaks dir . --no-banner --redact -v
8:38PM INF scanned ~7433732 bytes (7.43 MB) in 504ms
8:38PM INF no leaks found
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
  ok   template literal text: caught
  ok   template |safe output: caught
  ok   committed secret (gitleaks): caught
  ok   vulnerable pin (pip-audit): caught
  ok   disallowed licence: caught
guard self-test: 0 failing guard(s)
```
