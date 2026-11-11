# Phase 3 handoff: Storage, versioning, resumability

**Status: implemented, locally green. NOT complete:** CI on both OSes and your approval are outstanding, and
**P3-1 and P3-2** are open (see `EXECUTION_PLAN.md`, "Final phase: Pending items").

## What was built
- `storage/schema.py` (SSOT: names, types, version hash), `storage/manifest.py` (resume record, keyed by input hash +
  feature version + chunk settings), `storage/feature_store.py` (one Parquet file per chunk, append-only, verified on read),
  `storage/files.py` (confinement, atomic write, bounded read, hashing). `pyarrow` dependency (DECISIONS #42).
- `decode_chunks(start_chunk=)`: resume without decoding finished chunks (DECISIONS #45). `core/events.py` (log helper moved, #46).
- Decisions #42 to #47. Errors use `error.storage.*` keys in `strings.toml`.
- Evidence: kill-and-resume (`tests/integration/test_resume.py`): a real worker subprocess is SIGKILLed after 1, 5 and 11
  chunks (and twice in one run); the resumed run decodes exactly the unfinished chunks and the stored directory is byte-identical to an
  uninterrupted run. Determinism (`test_determinism.py`): two runs 1.1 s apart give byte-identical files. 30/30 repeated runs of
  the resume, determinism and decode integration tests passed; no ffmpeg orphans remained after kills. Tests and mypy also pass on Python 3.11.
- Guards: `test_atomic_writes.py` plus 9 probes (1 planted violation, 8 mutations), all caught.

## 1. Tech debt incurred, and 2. exact steps taken to resolve each item now
| # | Debt found in the Phase 3 review | Resolution (done) |
|---|---|---|
| 1 | Telemetry helper lived in `media/`, unusable by `storage/` (layer rules), tempting a duplicate | Pure part moved to `core/events.py`; `media/telemetry.py` keeps only `peak_rss_mb`; tests renamed |
| 2 | Resume test watchdog used non-daemon timers: pytest lingered 120 s after finishing | Timer is a daemon thread |
| 3 | `tree()` helper duplicated in two integration tests | Moved to `tests/integration/_pipeline.py` |
| 4 | Speculative `Manifest.new`; dead `is_dir()` branch in `open_directory`; test helpers using `# type: ignore` | Removed / typed properly |
| 5 | Coverage gaps (mkstemp failure, infinite end time) | Tests added; coverage 100% |
| 6 | pyarrow has no type stubs | mypy override confined to pyarrow (#42) instead of another dependency |
| 7 | Forcing resume with decode start 0 fails with `out_of_order` (append-only), not the "decoded" assertion | Accepted: append-only blocks it loudly; the seek itself has its own unit test and mutation probe |
| 8 | Test-only callers: `sha256_file`, `read_columns`, `mark_complete` have no production caller until Phase 4/6 | Not speculative: they are the contract those phases consume; noted, not removed |

### Unresolvable in Phase 3 (consolidated in `EXECUTION_PLAN.md`)
- **P3-1** Resume on real footage unverified (synthetic clip only); close in the Phase 4 real-clip smoke test.
- **P3-2** CI has not run: `ci.yml` only triggers on `main` pushes and PRs, so pushing the branch started nothing.

## 3. Build confirmation: raw `make ci` output (exit code 0, ANSI stripped)

```text
uv sync --locked
Resolved 70 packages in 3ms
Checked 69 packages in 1ms
/Applications/Xcode.app/Contents/Developer/usr/bin/make check
uv run --locked ruff check .
All checks passed!
uv run --locked ruff format --check .
83 files already formatted
uv run --locked mypy
Success: no issues found in 74 source files
uv run --locked pytest tests/unit tests/architecture tests/integration
============================= test session starts ==============================
platform darwin -- Python 3.12.14, pytest-9.2.0, pluggy-1.7.0
rootdir: /Users/sunil/Downloads/FilmAnalyser
configfile: pyproject.toml
plugins: platformdirs-4.14.5, hypothesis-6.170.15, cov-7.1.0
collected 407 items

tests/unit/test_chunk.py ............................                    [  6%]
tests/unit/test_chunker.py ..............                                [ 10%]
tests/unit/test_config.py ................                               [ 14%]
tests/unit/test_errors.py .........                                      [ 16%]
tests/unit/test_events.py ...........                                    [ 19%]
tests/unit/test_feature_store.py ...........................             [ 25%]
tests/unit/test_ffmpeg_stream.py .........                               [ 28%]
tests/unit/test_files.py .........................                       [ 34%]
tests/unit/test_manifest.py .............................                [ 41%]
tests/unit/test_paths.py ................                                [ 45%]
tests/unit/test_probe.py .................                               [ 49%]
tests/unit/test_registry.py ...............                              [ 53%]
tests/unit/test_resources.py ..........................                  [ 59%]
tests/unit/test_schema.py ..............................                 [ 66%]
tests/architecture/test_atomic_writes.py ....                            [ 67%]
tests/architecture/test_ci_workflow.py .........                         [ 70%]
tests/architecture/test_color_contrast.py ..........................     [ 76%]
tests/architecture/test_error_keys.py ....                               [ 77%]
tests/architecture/test_file_size.py ......                              [ 78%]
tests/architecture/test_frozen_dataclasses.py ....                       [ 79%]
tests/architecture/test_function_limits.py ...                           [ 80%]
tests/architecture/test_layer_imports.py ............                    [ 83%]
tests/architecture/test_no_hardcoded_colors.py ........                  [ 85%]
tests/architecture/test_no_hardcoded_strings.py ..........               [ 87%]
tests/architecture/test_security_patterns.py ..............              [ 91%]
tests/architecture/test_subprocess_argv.py .....                         [ 92%]
tests/integration/test_decode_stream.py ................                 [ 96%]
tests/integration/test_determinism.py ...                                [ 97%]
tests/integration/test_ffmpeg_version.py .                               [ 97%]
tests/integration/test_memory_flat.py ...                                [ 98%]
tests/integration/test_resume.py ......                                  [ 99%]
tests/integration/test_wheel_resources.py .                              [100%]

================================ tests coverage ================================
______________ coverage: platform darwin, python 3.12.14-final-0 _______________

Name    Stmts   Miss Branch BrPart  Cover   Missing
---------------------------------------------------
TOTAL     820      0    170      0   100%

28 files skipped due to complete coverage.
Required test coverage of 90% reached. Total coverage: 100.00%
============================= 407 passed in 13.11s =============================
mkdir -p .cache
uv export --locked --no-emit-project --format requirements-txt -o .cache/audit-requirements.txt >/dev/null
Resolved 70 packages in 2ms
uv run --locked pip-audit --require-hashes --disable-pip -r .cache/audit-requirements.txt
No known vulnerabilities found
uv run --locked pip-licenses --allow-only="MIT License;MIT;BSD License;BSD-2-Clause;BSD-3-Clause;Apache Software License;Apache-2.0;Apache-2.0 OR BSD-2-Clause;Python Software Foundation License;PSF-2.0;ISC License (ISCL);MPL-2.0;Mozilla Public License 2.0 (MPL 2.0);The Unlicense (Unlicense);BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0" --format=plain >/dev/null
gitleaks dir . --no-banner --redact -v
9:12PM INF scanned ~2388881 bytes (2.39 MB) in 154ms
9:12PM INF no leaks found
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
  ok   template literal text: caught
  ok   template |safe output: caught
  ok   committed secret (gitleaks): caught
  ok   vulnerable pin (pip-audit): caught
  ok   disallowed licence: caught
guard self-test: 0 failing guard(s)
```
