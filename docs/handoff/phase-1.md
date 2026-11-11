# Phase 1 handoff: Foundation and guardrails

**Status: built and green locally. NOT closed:** two items need a GitHub remote (P1-1, P1-2, listed
in "Final phase: Pending items" in `EXECUTION_PLAN.md`).

## 1. Tech debt incurred, and 2. exact steps taken to resolve each item now

| # | Debt found during the Phase 1 review | Resolution (done) |
|---|---|---|
| 1 | Three near-identical test helpers (`_tree`, `_py`, `_write`): rule-of-three DRY violation | Added `make_package()` to `tests/architecture/_scan.py`, deleted the three copies, rewrote their call sites |
| 2 | `scripts/guard_probes.py::source_probes` was 79 lines. The new function-length guard caught it on its own author | Split into `architecture_probes`, `security_probes`, `quality_probes` (+ `source_probes` combiner) |
| 3 | Suppression-comment guard matched `# nosec` inside string literals (false positive) | Now reads real comment tokens via `tokenize`; added a test for the string case |
| 4 | Guard self-test could "pass" for the wrong reason (the gitleaks probe failed because its output never names the file) | Every probe carries an `expect` marker that must appear in the failing output; gitleaks run with `-v` in both `make secrets` and the probe |
| 5 | Bandit B404/B603 noise on legitimate argument-list `subprocess` | Skipped at config level only (`pyproject.toml`), shell variants left on, inline `# nosec` banned by a guard; DECISIONS #24 |
| 6 | Licence allowlist used `--partial-match` (too loose); pip-audit had a redundant `--no-deps` | Explicit exact-match allowlist taken from the actual locked environment; flag removed |
| 7 | `_toml.py` error path uncovered (87%) | Added `test_missing_packaged_file_raises`; coverage now 100% |
| 8 | `requires-python >=3.11` was only exercised on 3.12 | Ran tests + mypy on 3.11 (`uv run --python 3.11`): 142 passed, mypy clean; DECISIONS #32 |
| 9 | SRP-exception regex demanded 10 contiguous non-space characters (rejected a legitimate reason) | Regex now requires a reason of 13+ characters; tests cover accepted, empty and placeholder reasons |
| 10 | Pre-commit hooks and Conventional Commits check were configured but unproven | Installed (`make hooks`); a non-Conventional message and a hard-coded-colour change were both rejected by the hooks |

### Planned sequencing (in the plan's own later phases, so not debt)
- `Extractor.extract(chunk: object)` is narrowed to `Chunk` in Phase 2 (DECISIONS #25).
- Registry auto-discovery arrives with the first real extractors in Phase 4 (DECISIONS #25).
- ffmpeg install in CI starts in Phase 2 (DECISIONS #29); SBOM and Dependabot in Phase 8 (DECISIONS #30).

### Unresolvable in Phase 1 (fail-loud; consolidated in `EXECUTION_PLAN.md`, "Final phase: Pending items")
- **P1-1** CI has never run on GitHub: no remote exists. The workflow is structurally tested only.
- **P1-2** Branch protection is not applied (instructions in `docs/BRANCH_PROTECTION.md`).

Also noted: `prd.md` (empty, pre-existing) is left untracked and untouched.

## 3. Build confirmation: raw `make ci` output (exit code 0)

```text
uv sync --locked
Resolved 67 packages in 22ms
Checked 67 packages in 7ms
/Applications/Xcode.app/Contents/Developer/usr/bin/make check
uv run --locked ruff check .
All checks passed!
uv run --locked ruff format --check .
45 files already formatted
uv run --locked mypy
Success: no issues found in 38 source files
uv run --locked pytest tests/unit tests/architecture tests/integration
============================= test session starts ==============================
platform darwin -- Python 3.12.14, pytest-9.2.0, pluggy-1.7.0
rootdir: /Users/sunil/Downloads/FilmAnalyser
configfile: pyproject.toml
plugins: platformdirs-4.14.5, hypothesis-6.170.15, cov-7.1.0
collected 143 items

tests/unit/test_config.py .......                                        [  4%]
tests/unit/test_errors.py ......                                         [  9%]
tests/unit/test_registry.py ..............                               [ 18%]
tests/unit/test_resources.py ..........................                  [ 37%]
tests/architecture/test_ci_workflow.py ......                            [ 41%]
tests/architecture/test_color_contrast.py ..........................     [ 59%]
tests/architecture/test_file_size.py ......                              [ 63%]
tests/architecture/test_frozen_dataclasses.py ....                       [ 66%]
tests/architecture/test_function_limits.py ...                           [ 68%]
tests/architecture/test_layer_imports.py ............                    [ 76%]
tests/architecture/test_no_hardcoded_colors.py ........                  [ 82%]
tests/architecture/test_no_hardcoded_strings.py ..........               [ 89%]
tests/architecture/test_security_patterns.py ..............              [ 99%]
tests/integration/test_wheel_resources.py .                              [100%]

================================ tests coverage ================================
______________ coverage: platform darwin, python 3.12.14-final-0 _______________

Name    Stmts   Miss Branch BrPart  Cover   Missing
---------------------------------------------------
TOTAL     187      0     30      0   100%

17 files skipped due to complete coverage.
Required test coverage of 90% reached. Total coverage: 100.00%
============================= 143 passed in 0.62s ==============================
mkdir -p .cache
uv export --locked --no-emit-project --format requirements-txt -o .cache/audit-requirements.txt >/dev/null
Resolved 67 packages in 2ms
uv run --locked pip-audit --require-hashes --disable-pip -r .cache/audit-requirements.txt
No known vulnerabilities found
uv run --locked pip-licenses --allow-only="MIT License;MIT;BSD License;BSD-2-Clause;BSD-3-Clause;Apache Software License;Apache-2.0;Apache-2.0 OR BSD-2-Clause;Python Software Foundation License;PSF-2.0;ISC License (ISCL);MPL-2.0;Mozilla Public License 2.0 (MPL 2.0);The Unlicense (Unlicense)" --format=plain >/dev/null
gitleaks dir . --no-banner --redact -v
5:51PM INF scanned ~1077967 bytes (1.08 MB) in 76.1ms
5:51PM INF no leaks found
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
  ok   template literal text: caught
  ok   template |safe output: caught
  ok   committed secret (gitleaks): caught
  ok   vulnerable pin (pip-audit): caught
  ok   disallowed licence: caught
guard self-test: 0 failing guard(s)
```
