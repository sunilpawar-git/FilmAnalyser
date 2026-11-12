# Phase 4 handoff: Video extractors and walking skeleton

**Status: implemented; CI green on macOS and Linux (run 43171687495, PR #4).** P3-1 (resume on real footage) is **closed**. The phase is **not complete** until P4-1 is closed: the nightly real-clip job needs the repository variables `REAL_CLIP_URL` and `REAL_CLIP_SHA256`, which you set. Then your approval. See `EXECUTION_PLAN.md`, "Final phase: Pending items".

## What was built
- **Extractors** (`extractors/`, core imports only): `shot_cuts` (hard cuts from soft colour histograms, boundary rule in DECISIONS #55), `color` (brightness, contrast, colourfulness, warmth, letterbox), `letterbox` (a helper, no `EXTRACTOR`: bars from the median row brightness over the chunk). No OpenCV (DECISIONS #51).
- **Contract and registry**: `Extractor.features` declared per extractor (DECISIONS #49); `discover()` finds every module with an `EXTRACTOR` (DECISIONS #50); the feature schema is built from the registry (`pipeline/runner.schema_for`), so `storage/schema.py` lists no feature.
- **Pipeline** (`pipeline/runner.py`): decode, extract every registered extractor, store, resume at the store's next chunk. Refuses an overlap below one frame (DECISIONS #55). Replaces the Phase 3 stand-in `tests/integration/_pipeline.py`, which is deleted.
- **P3-1 fix** (`media/ffmpeg_stream.py`, DECISIONS #54): see Evidence.
- **Report** (`report/`): `viewmodel.py` (pure: numbers and chart coordinates), `renderer.py` (Jinja2, autoescape on), `templates/report.html` (one inline SVG chart, CSP `default-src 'none'`, no script), `resources/layout.py` (packaged file names). Text from `strings.toml`, colours from `colors.toml`.
- **CLI** (`cli/main.py`): `filmanalyser FILM --out DIR [--report FILE] [-v]`. Exit codes follow the taxonomy: 2 input, 3 decode or missing ffmpeg, 5 storage, 1 other. Prints the message for an error key, never a traceback.
- **Core**: `core/features.py` (column names, one definition for store, view model and extractors); `core/config.py` (the new thresholds: `CUT_DISTANCE`, `HIST_BINS`, `LETTERBOX_LUMA`, `LUMA_WEIGHTS`, `EXTRACT_BUDGET_FRACTION`).
- **CI and workflows**: `.github/actions/setup-ffmpeg` (the single home of the ffmpeg pins and checksums, used by `ci.yml` and `nightly.yml`; the action also checks the installed version against the pin); `.github/workflows/nightly.yml` (`make nightly` on both OSes; the real-clip job runs only when `REAL_CLIP_URL` is set, and verifies `REAL_CLIP_SHA256`). Make targets: `make nightly`, `make real-clip`.
- **Guards**: `tests/architecture/test_no_skips.py` (DECISIONS #58), `test_nightly_workflow.py`, `scripts/guard_probes_phase4.py` (3 planted violations and 6 mutations, all caught).
- **Dependency**: `jinja2` 3.1.6 with `markupsafe` 3.0.4 (DECISIONS #52). Licence BSD-3-Clause; pip-audit clean; in `uv.lock`.

## 1. Tech debt incurred and found, and 2. exact steps taken to resolve each item

| # | Debt (found during the phase) | Resolution (done, verified in `make check`) |
|---|---|---|
| 1 | **Real defect, P3-1:** the decoder re-anchored the 12 fps grid to the first frame decoded after a seek (`setpts=PTS-STARTPTS`). A resumed run then sampled different frames whenever a seek point fell between source frames | Anchored to the stream's own start from the probe (`setpts=PTS-<start>/TB`), with `-copyts` keeping the container clock. Tests: `test_resume_grid.py` (25 and 30 fps, every resume point), a mutation probe that reinstates `PTS-STARTPTS` (caught), and the real-footage kill-and-resume run (below) |
| 2 | My first draft of DECISIONS #54 gave the wrong mechanism (seek re-basing). Measured: removing `-copyts` alone changes nothing | Corrected in DECISIONS #54 and in the code comment and docstrings before commit; the mutation probe targets the real cause, not the flag |
| 3 | Stand-in pipeline `tests/integration/_pipeline.py` duplicated the runner | Deleted. Tests call `analyse()`; `tree()` and the shared `CONFIG` moved to `tests/fixtures/store.py` |
| 4 | Kill-and-resume harness duplicated (synthetic and real clip), and two near-identical worker modules | One harness, `tests/integration/_kill.py`; one worker, `_resume_worker.py`, with a `profile` argument; `_real_clip_worker.py` deleted |
| 5 | ffmpeg pins duplicated between `ci.yml` and the new nightly workflow | One composite action, `.github/actions/setup-ffmpeg`, with the pins once; it now checks the installed version against the pin, so a wrong binary fails the build |
| 6 | Two root-dependent `@pytest.mark.skipif(os.geteuid() == 0)` tests (`test_paths.py`): a skip on root, and a rule breach (no skips) | Rewritten to simulate the permission failure (`monkeypatch` of `os.access` and of `Path.resolve`), so they run everywhere and cannot skip |
| 7 | `-v` attached a stream handler to the library logger and never removed it. A later test failed on a closed capture stream (order-dependent failure) | `_events_to_stderr` is a context manager that restores the handler and level on exit |
| 8 | Column names (`start_s`, `shot_cuts.cuts`) written in the view model: a second copy of names the store owns | `core/features.py` is the one definition; `storage/schema.py` imports it |
| 9 | Mutable accumulator dataclass in `color.py` (frozen-dataclass rule) | Plain local sums in `picture_features`; the `_sums` helper is pure |
| 10 | `guard_probes.py` reached 372 lines, and two functions exceeded 40 lines | Phase 4 probes moved to `scripts/guard_probes_phase4.py`; `media_mutations` split into two functions |
| 11 | Duplicate encoder options in the two ffmpeg clip builders | `VIDEO_ENCODE` once in `tests/fixtures/make_synthetic.py` |
| 12 | Hand-written name validation in the registry | One regex (`_NAME`) |
| 13 | YAGNI and a trap in `analyse()`: an injectable registry no caller used, and a `Config()` default argument (B008) | Removed the injection; `config: Config \| None = None` |
| 14 | Ground-truth trap: `ffmpeg` rounds each scene's duration **up** to whole frames, so cut times written in seconds were wrong (measured: 273 frames where 270.24 s were requested). Found by an accuracy check, not by a test | `cut_times` and `cut_clip_argv` refuse durations that are not whole frames (`_whole_frames`); off-grid precision/recall tests added at 24 and 25 fps with frame-exact truth |
| 15 | Existing decoder tests asserted the old mechanism (`setpts=PTS-STARTPTS`) | Updated to the measured mechanism, docstrings included |
| 16 | The literal-string guard would have forced every argparse flag and column key into `strings.toml` | A narrow, explicit rule for technical tokens only (flags, format specs, dotted or underscored identifiers); plain words still fail. The `film` argument name moved to `strings.toml` (it is in the usage line) |
| 17 | A renderer test looked for `var(--text)` outside `<style>`, where it is not | Test corrected; the token use is asserted in the page |
| 18 | `strings.toml`: during an edit, the `[cli]` keys landed under `[chart.cut_rate]` (found by reading the file) | Moved back into `[cli]`; the file was re-read and the table headers re-checked |
| 19 | The real-clip test imported its config from a test module, and the worker imported the test module back | Config lives in the worker's profile table (`_resume_worker.PROFILES`) |
| 20 | `EXECUTION_PLAN.md`: a pending-table row merged into a sentence, and blank lines split the table | Fixed; the table renders as one block |

### Unresolvable in Phase 4 (fail loudly; consolidated in `EXECUTION_PLAN.md`)
- **P4-1 (open)** The nightly real-clip job is configured but inactive until the repository variables `REAL_CLIP_URL` and `REAL_CLIP_SHA256` are set. That is a repository settings change; I did not make it.
- **P4-2 (closed)** CI on both OSes: run 43171687495, both jobs green. The Linux job ran ffmpeg 6.0.1 (the version check passed); macOS ran 9.0.2. This machine has only 9.0.2; the 6.0.1 run is CI's, not local (house rule: no downloaded binary was executed here).

### Known limitations (documented, not debt)
- **Hard cuts only.** Fades and dissolves are not detected (no ground truth for them in the synthetic set); the real-footage check is Phase 8.
- **Accuracy is measured on synthetic clips only.** On the real excerpt there are no hand labels: the detector reports 31 hard cuts in 5 minutes. That number is a sanity figure, not a validated accuracy.
- **Letterbox** is a median-brightness rule per chunk. A chunk of mostly dark picture can be read as bars; a single dark flash is not (tested).
- **No colour palette yet** (the report shows cuts only, as the walking skeleton requires). Palette and the full report are Phase 7.
- **Features are per chunk.** Cut times are not stored, only counts; the chart is cuts per minute per chunk.

## 3. Build confirmation: raw `make check` output (ANSI stripped)
`make check` exited 0 on this tree. Counts: 482 passed, 4 deselected (1 `real_clip`, 3 `slow`), 0 skipped, coverage 100.00%, guard self-test 0 failing (48 probes caught).

```text
uv run --locked ruff check .
All checks passed!
uv run --locked ruff format --check .
107 files already formatted
uv run --locked mypy
Success: no issues found in 97 source files
uv run --locked pytest tests/unit tests/architecture tests/integration -m "not real_clip and not slow"
============================= test session starts ==============================
platform darwin -- Python 3.12.14, pytest-9.2.0, pluggy-1.7.0
rootdir: /Users/sunil/Downloads/FilmAnalyser
configfile: pyproject.toml
plugins: platformdirs-4.14.5, hypothesis-6.170.15, cov-7.1.0
collected 486 items / 4 deselected / 482 selected
tests/unit/test_chunk.py ............................                    [  5%]
tests/unit/test_chunker.py ..............                                [  8%]
tests/unit/test_color.py .........                                       [ 10%]
tests/unit/test_config.py ................                               [ 13%]
tests/unit/test_errors.py .........                                      [ 15%]
tests/unit/test_events.py ...........                                    [ 18%]
tests/unit/test_feature_store.py ...........................             [ 23%]
tests/unit/test_ffmpeg_stream.py ..........                              [ 25%]
tests/unit/test_files.py .........................                       [ 30%]
tests/unit/test_letterbox.py .....                                       [ 31%]
tests/unit/test_manifest.py .............................                [ 37%]
tests/unit/test_paths.py ................                                [ 41%]
tests/unit/test_probe.py .................                               [ 44%]
tests/unit/test_registry.py .....................                        [ 49%]
tests/unit/test_renderer.py .......                                      [ 50%]
tests/unit/test_resources.py ..........................                  [ 56%]
tests/unit/test_runner.py ......                                         [ 57%]
tests/unit/test_schema.py ..............................                 [ 63%]
tests/unit/test_shot_cuts.py ..........                                  [ 65%]
tests/unit/test_viewmodel.py ......                                      [ 66%]
tests/architecture/test_atomic_writes.py ....                            [ 67%]
tests/architecture/test_ci_workflow.py ..........                        [ 69%]
tests/architecture/test_color_contrast.py ..........................     [ 75%]
tests/architecture/test_error_keys.py ....                               [ 75%]
tests/architecture/test_file_size.py ......                              [ 77%]
tests/architecture/test_frozen_dataclasses.py ....                       [ 78%]
tests/architecture/test_function_limits.py ...                           [ 78%]
tests/architecture/test_layer_imports.py ............                    [ 81%]
tests/architecture/test_nightly_workflow.py .......                      [ 82%]
tests/architecture/test_no_hardcoded_colors.py ........                  [ 84%]
tests/architecture/test_no_hardcoded_strings.py ..........               [ 86%]
tests/architecture/test_no_skips.py ...                                  [ 86%]
tests/architecture/test_security_patterns.py ..............              [ 89%]
tests/architecture/test_subprocess_argv.py .....                         [ 90%]
tests/integration/test_cli.py .....                                      [ 91%]
tests/integration/test_decode_stream.py ................                 [ 95%]
tests/integration/test_determinism.py ...                                [ 95%]
tests/integration/test_extract_budget.py .                               [ 96%]
tests/integration/test_ffmpeg_version.py .                               [ 96%]
tests/integration/test_memory_flat.py ...                                [ 96%]
tests/integration/test_resume.py ......                                  [ 98%]
tests/integration/test_resume_grid.py ..                                 [ 98%]
tests/integration/test_video_pipeline.py ......                          [ 99%]
tests/integration/test_wheel_resources.py .                              [100%]
================================ tests coverage ================================
______________ coverage: platform darwin, python 3.12.14-final-0 _______________
Name    Stmts   Miss Branch BrPart  Cover   Missing
---------------------------------------------------
TOTAL    1112      0    204      0   100%
37 files skipped due to complete coverage.
Required test coverage of 90% reached. Total coverage: 100.00%
====================== 482 passed, 4 deselected in 18.28s ======================
mkdir -p .cache
uv export --locked --no-emit-project --format requirements-txt -o .cache/audit-requirements.txt >/dev/null
Resolved 70 packages in 3ms
uv run --locked pip-audit --require-hashes --disable-pip -r .cache/audit-requirements.txt
No known vulnerabilities found
uv run --locked pip-licenses --allow-only="MIT License;MIT;BSD License;BSD-2-Clause;BSD-3-Clause;Apache Software License;Apache-2.0;Apache-2.0 OR BSD-2-Clause;Python Software Foundation License;PSF-2.0;ISC License (ISCL);MPL-2.0;Mozilla Public License 2.0 (MPL 2.0);The Unlicense (Unlicense);BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0" --format=plain >/dev/null
gitleaks dir . --no-banner --redact -v
12:19PM INF scanned ~3197952 bytes (3.20 MB) in 177ms
12:19PM INF no leaks found
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
  ok   template literal text: caught
  ok   template |safe output: caught
  ok   committed secret (gitleaks): caught
  ok   vulnerable pin (pip-audit): caught
  ok   disallowed licence: caught
guard self-test: 0 failing guard(s)
```

## Evidence

**P3-1, real footage** (`make real-clip`, `FILMANALYSER_REAL_CLIP` set to a 5-minute excerpt of a 1920x1080, 23.976 fps film, kept outside the repo):
- Passed: reference run (30 chunks of 10.25 s at 12 fps), a SIGKILL after the third stored chunk, a resume from the store's next chunk, and every stored column equal to the reference. 15.5 s in total. (The synthetic resume tests assert which chunks are decoded; this test asserts the equality that matters.)
- The same test with the bug reinstated (`PTS-STARTPTS`) fails: `AssertionError: column end_s differs after resume`. The fixed file is restored and byte-identical to the backup.

**P3-1, synthetic** (CI-safe): before the fix, 25 and 30 fps sources with 10.25 s chunks gave different frames at resume points; after it, every resume point matches (`test_resume_grid.py`).

**Cut detection, precision and recall** (synthetic clips, frame-exact ground truth, tolerance one analysis frame = 0.083 s):

| Source fps | Cuts | Precision | Recall | Max timing error |
|---|---|---|---|---|
| 12 (on the grid) | 3 | 1.00 | 1.00 | 0.000 s |
| 24 (off the grid) | 4 | 1.00 | 1.00 | 0.042 s |
| 25 (off the grid) | 3 | 1.00 | 1.00 | 0.040 s |

Property test (Improvement 4): for any chunk size from 4 to 30 frames and any overlap from 1 to 3 frames, the cuts found chunk by chunk equal the cuts on the whole film (60 hypothesis examples). Boundary test: a cut on a chunk's first core frame is counted once.

**Walking skeleton on real footage** (`filmanalyser`, default 60 s chunks, the 5-minute excerpt): 6 chunks, 31 hard cuts, report written; peak RSS 157.8 MB (budget 2 GB); 8.3 s wall time for 5 minutes of film; extraction 2.72 s in total, at most 0.62 s for any one chunk (budget: a quarter of the chunk duration, `test_extract_budget.py`).

**Flakiness** (process, kill and timing tests run repeatedly on this machine): loop A (resume, kill, grid, CLI, budget, determinism, video pipeline, ffmpeg stream) and loop B (memory flatness, 10x), 30 runs each. Loop B: 0 failures in 30. Loop A (final code, all 30 runs, run after every change above): 0 failures in 30.

**Dependency** (DECISIONS #52): Jinja2 3.1.6 wheel 135 kB, MarkupSafe 3.0.4 arm64 wheel 12 kB, installed 1.1 MB + 108 kB; `import jinja2` 21 ms warm (median of five), renderer import 57 ms.

## Decisions added (`DECISIONS.md` #49 to #58)
49 features declared on the protocol · 50 registry discovery · 51 numpy only, hard cuts · 52 Jinja2 renderer (measured) · 53 real-clip marker, never a skip · 54 P3-1 fix (mechanism corrected) · 55 overlap of at least one frame · 56 walking-skeleton scope · 57 constants and their basis · 58 composite action and no-skips guard.

## CI (PR #4)
Run 43171687495: `make check (macos-latest)` and `make check (ubuntu-latest)` both green. Linux: `ffmpeg version 6.0.1-static`, version check passed, `test_resume_grid.py` passed. macOS: `ffmpeg version 9.0.2`. Both: 482 passed, 4 deselected, coverage 100%.

## Next
Set the repository variables `REAL_CLIP_URL` and `REAL_CLIP_SHA256` to close P4-1 (or tell me to leave it open). Then your approval: `make ship` (rebase-merge once green), `make tag-phase N=4 PR=4`, and the explicit push of the tag. Nothing else starts before that approval (no Phase 5).
