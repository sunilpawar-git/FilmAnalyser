# Phase 2 handoff: Core contracts and streaming decoder

**Status: built and green locally. NOT closed.** P2-1 and P2-2 (and the inherited P1-2) are open;
all three are listed in "Final phase: Pending items" in `EXECUTION_PLAN.md`.

## What was built
- `core/chunk.py`: `Chunk` (frozen, read-only frames, core window + leading overlap), `ChunkSpan`,
  `span_for` (the single source of the overlap maths), `expected_chunks`, `frames_for`.
- `core/extractor.py`: `Extractor.extract(chunk: Chunk)` (DECISIONS #25, #34). Registry and dummy tests updated.
- `core/config.py`: `overlap_seconds`, `analysis_fps`, `frame_width`, derived frame counts, geometry validation, and the tool security bounds.
- `core/errors.py`: errors carry a message `key` + `fields` (no English text); `strings.toml` holds the messages (DECISIONS #35).
- `media/paths.py` (path validation, tool lookup, stderr scrub), `media/probe.py` (ffprobe), `media/ffmpeg_stream.py`
  (streaming decode), `media/chunker.py`, `media/telemetry.py` (structured logging, RSS).
- `numpy` runtime dependency (DECISIONS #33), `uv.lock` updated, pip-audit and licence checks clean.
- `.github/workflows/ci.yml`: ffmpeg install (Linux pinned + checksummed + cached; macOS Homebrew), README requirements.
- Decisions appended: #33 to #38.

## 1. Tech debt incurred, and 2. exact steps taken to resolve each item now

| # | Debt found during the Phase 2 review | Resolution (done) |
|---|---|---|
| 1 | **Real bug, intermittent:** the stderr drain thread could read a pipe that `Popen.__exit__` had already closed (`PytestUnhandledThreadExceptionWarning`, seen once in `make check`) | `_StderrTail.finish()` joins the thread before the pipes close (in the `finally`, after the kill); the thread also stops quietly on a closed pipe (`contextlib.suppress`). Stressed: 40 of 40 runs of the three stream tests passed |
| 2 | Integration tests used `skipif(no ffmpeg)`, contradicting "no skips" (and DECISIONS #38 as first drafted) | Removed; `tests/integration/conftest.py` fails the session loudly. Proven: with ffmpeg off `PATH`, 13 integration tests error |
| 3 | The stderr limit existed twice (4096 in `ffmpeg_stream`, 2000 in `probe`) and probe timeouts lived in `media/`, against the "constants once in `core/config.py`" rule | `STDERR_LIMIT_BYTES`, `PROBE_TIMEOUT_S`, `PROBE_MAX_OUTPUT_BYTES` now live in `core/config.py`; both modules import them |
| 4 | `Config.frames_per_chunk` re-implemented `frames_for` (DRY) | It now calls `frames_for` |
| 5 | Error messages were free English text in exceptions, which the "no hardcoded strings / new errors need a key" rule forbids | Key + fields design; `Config` and `Chunk` migrated; every key is checked against `strings.toml` by `tests/architecture/test_error_keys.py`; category keys renamed `error.<category>.default` (TOML cannot hold a string and a table at the same key) |
| 6 | numpy's compound licence (`BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0`) failed the exact-match allowlist | Exact string added to the `Makefile` allowlist with a note (all parts permissive); DECISIONS #33 |
| 7 | Two coverage gaps after the first full run (`PermissionError` branch of path validation, non-finite duration in the probe parser) | Two tests added; coverage is 100% |
| 8 | The memory-flatness worker only worked when pytest ran from the repo root | `cwd=REPO` set explicitly |
| 9 | ffmpeg has no `--` for inputs, so the plan's "paths after `--`" cannot be applied literally to ffmpeg | Equivalent protection built and recorded (DECISIONS #36): absolute validated path, `file:` prefix, `-protocol_whitelist file`; ffprobe does use `--`. Covered by unit tests and by four mutation probes in the guard self-test |
| 10 | Python 3.11 floor unverified for the new code | Tests and `mypy --strict` run on 3.11 (separate env): 276 passed, mypy clean |
| 11 | DECISIONS #38 was first drafted claiming exact CI pinning on both OSes | Corrected before commit to say what is actually built; the gap is tracked as P2-2 |

### Unresolvable in Phase 2 (fail-loud; consolidated in `EXECUTION_PLAN.md`, "Final phase: Pending items")
- **P2-1** (closed after the push, see the plan) The CI ffmpeg steps have never run on GitHub. Pushing is outward-facing and was not approved. The Linux job uses ffmpeg 6.0.1; all local runs used 9.0.2.
- **P2-2** macOS CI ffmpeg (Homebrew) is not exactly pinned; only a floor (major >= 6) is enforced and the version is logged.
- **P1-2** (inherited) Branch protection on `main` is not applied. P1-1 was closed after Phase 1 (repo and green CI exist).

### Notes (not debt)
- `VideoInfo.start_s` and `expected_chunks` are used by tests only (they are the oracles for the pts-normalisation and chunk-count checks); no speculative production code beyond them.
- `media/telemetry.py` uses the POSIX `resource` module. Windows is an explicit non-goal for the MVP.
- `prd.md` (empty, pre-existing) is untracked and untouched.

## RSS flatness (measured)
**Correction after the first CI run:** macOS CI plateaued far slower than the laptop (12 chunks: 66-70 MB;
120 chunks: 89 MB, flat from chunk 64 at 89.3 to chunk 120 at 89.4), so the original "10x vs 1x" comparison
failed on warm-up, not growth. The test now asserts the peak stops rising after chunk 64 (DECISIONS #39).
The numbers below are the original local measurements.
Test (`tests/integration/test_memory_flat.py`, 10 s chunks, each film in its own process):
12 chunks to 46.7 MB, 120 chunks (10x longer) to 47.5 MB. Budget: 10 % + 8 MB.

Production settings (60 s chunks, 12 fps, 160 px), manual run, same machine:

| Film | Chunks | Peak RSS |
|---|---|---|
| 2 min | 2 | 95.5 MB (warm-up: not yet at steady state) |
| 6 min | 6 | 126.2 MB |
| 10 min | 10 | 127.2 MB |
| 40 min | 40 | 127.2 MB |
| 80 min | 80 | 127.2 MB |
| 20 min, **control: keeps every chunk** | 20 | 484.1 MB (growth the test would catch) |

## 3. Build confirmation: raw `make ci` output (exit code 0)

```text
uv sync --locked
Resolved 69 packages in 3ms
Checked 68 packages in 1ms
/Applications/Xcode.app/Contents/Developer/usr/bin/make check
uv run --locked ruff check .
All checks passed!
uv run --locked ruff format --check .
68 files already formatted
uv run --locked mypy
Success: no issues found in 59 source files
uv run --locked pytest tests/unit tests/architecture tests/integration
============================= test session starts ==============================
platform darwin -- Python 3.12.14, pytest-9.2.0, pluggy-1.7.0
rootdir: /Users/sunil/Downloads/FilmAnalyser
configfile: pyproject.toml
plugins: platformdirs-4.14.5, hypothesis-6.170.15, cov-7.1.0
collected 276 items

tests/unit/test_chunk.py ............................                    [ 10%]
tests/unit/test_chunker.py ..........                                    [ 13%]
tests/unit/test_config.py ................                               [ 19%]
tests/unit/test_errors.py .........                                      [ 22%]
tests/unit/test_ffmpeg_stream.py ........                                [ 25%]
tests/unit/test_paths.py ................                                [ 31%]
tests/unit/test_probe.py .................                               [ 37%]
tests/unit/test_registry.py ...............                              [ 43%]
tests/unit/test_resources.py ..........................                  [ 52%]
tests/unit/test_telemetry.py ...........                                 [ 56%]
tests/architecture/test_ci_workflow.py .........                         [ 59%]
tests/architecture/test_color_contrast.py ..........................     [ 69%]
tests/architecture/test_error_keys.py ....                               [ 70%]
tests/architecture/test_file_size.py ......                              [ 72%]
tests/architecture/test_frozen_dataclasses.py ....                       [ 74%]
tests/architecture/test_function_limits.py ...                           [ 75%]
tests/architecture/test_layer_imports.py ............                    [ 79%]
tests/architecture/test_no_hardcoded_colors.py ........                  [ 82%]
tests/architecture/test_no_hardcoded_strings.py ..........               [ 86%]
tests/architecture/test_security_patterns.py ..............              [ 91%]
tests/architecture/test_subprocess_argv.py .....                         [ 93%]
tests/integration/test_decode_stream.py ..............                   [ 98%]
tests/integration/test_ffmpeg_version.py .                               [ 98%]
tests/integration/test_memory_flat.py ...                                [ 99%]
tests/integration/test_wheel_resources.py .                              [100%]

================================ tests coverage ================================
______________ coverage: platform darwin, python 3.12.14-final-0 _______________

Name    Stmts   Miss Branch BrPart  Cover   Missing
---------------------------------------------------
TOTAL     490      0     92      0   100%

23 files skipped due to complete coverage.
Required test coverage of 90% reached. Total coverage: 100.00%
============================= 276 passed in 6.67s ==============================
mkdir -p .cache
uv export --locked --no-emit-project --format requirements-txt -o .cache/audit-requirements.txt >/dev/null
Resolved 69 packages in 3ms
uv run --locked pip-audit --require-hashes --disable-pip -r .cache/audit-requirements.txt
No known vulnerabilities found
uv run --locked pip-licenses --allow-only="MIT License;MIT;BSD License;BSD-2-Clause;BSD-3-Clause;Apache Software License;Apache-2.0;Apache-2.0 OR BSD-2-Clause;Python Software Foundation License;PSF-2.0;ISC License (ISCL);MPL-2.0;Mozilla Public License 2.0 (MPL 2.0);The Unlicense (Unlicense);BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0" --format=plain >/dev/null
gitleaks dir . --no-banner --redact -v
6:47PM INF scanned ~1763762 bytes (1.76 MB) in 104ms
6:47PM INF no leaks found
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
  ok   template literal text: caught
  ok   template |safe output: caught
  ok   committed secret (gitleaks): caught
  ok   vulnerable pin (pip-audit): caught
  ok   disallowed licence: caught
guard self-test: 0 failing guard(s)
```
