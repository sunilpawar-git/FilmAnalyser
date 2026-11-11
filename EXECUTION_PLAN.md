# Execution Plan

Builds on `README.md`, `DECISIONS.md`, `ACCEPTANCE.md`, `BACKLOG.md`. Scope is the MVP only (CLI + static HTML report).

## 0. Rules and how they are enforced

| Rule | Mapping to this project | Enforcement (automated, part of `make check`) |
|---|---|---|
| Phase ends with a green build | "Build" = `make check`: ruff, mypy --strict, pytest, bandit, pip-audit, wheel build | A phase cannot close unless `make check` exits 0 |
| TDD, 100% tests pass | Tests are written first per slice. Unit tests per module, integration tests per pipeline stage | pytest + coverage gate (>= 90% on new code); zero failures or skips allowed |
| MVVM | **Model** = typed feature schema, domain objects (`core/`, `storage/`, `analysis/`). **ViewModel** = pure-Python report view models, no formatting or I/O (`report/viewmodel.py`). **View** = HTML templates + CLI renderer, with no logic beyond loops and lookups | Architecture test: `analysis/` and `core/` may not import `report/`; views may not import `analysis/` |
| SOLID / DRY / SSOT | Extractors implement one `Extractor` protocol (open for extension). Constants and thresholds are defined once in `core/config.py`; schema version and feature names once in `storage/schema.py` | Architecture test + ruff duplicate-code review at each handoff |
| 300 LOC cap | Split by responsibility | `tests/architecture/test_file_size.py` fails on any `.py`/`.html`/`.toml` > 300 lines unless it has a top-of-file `# SRP-EXCEPTION: <why this file must not be split>` |
| No hardcoded strings or colours | All user-facing text lives in `report/resources/strings.toml` (and CLI messages in the same file). All colours are design tokens in `report/resources/colors.toml`, emitted as CSS variables, with dark mode | Architecture tests: no hex/rgb literals outside `colors.toml`; no user-facing string literals in `cli/` and `report/` outside resource lookups; templates may only reference `{{ t.key }}` and `var(--token)` |
| Security | Local-only, no network. No `shell=True`. No pickle. Validated paths. Escaped HTML output | bandit, pip-audit, a custom test that greps for `shell=True`, `pickle`, `eval`, `exec`, `requests`/`urllib` use, and Jinja autoescape tests |
| Simplicity (KISS, YAGNI, rule of three) | Build only what the current phase's acceptance criteria need; abstract only after a pattern appears three times; composition and `Protocol` over inheritance; no metaprogramming | ruff complexity rules: cyclomatic complexity <= 10, function length <= 40 lines, <= 5 arguments (PLR/C901 rules, failing the build); handoff review checks for speculative code |
| Pure core, thin shell | `analysis/` and `core/` are pure functions over immutable data; I/O (ffmpeg, disk, CLI) lives only in `media/`, `storage/`, `pipeline/`, `cli/` | Architecture test: pure layers may not import `subprocess`, `pathlib` I/O, `os`, or `sys`; data classes are `@dataclass(frozen=True)` |
| Scalability | Streaming by default; idempotent, resumable stages cached by input hash + feature version; extractors added through a registry with no edits to existing files (open/closed) | RAM-flatness test, determinism test, per-chunk time budget test, registry test (a dummy extractor registers without touching existing modules) |

### Toolchain
`uv` (env + hashed lock), Python 3.11+, `ruff`, `mypy --strict`, `pytest` + `pytest-cov` + `hypothesis`, `bandit`, `pip-audit`, `gitleaks` (secret scan), `pip-licenses` (allowlist), `cyclonedx-py` (SBOM), `pre-commit`, `make`.

### CI/CD
- **One definition of green:** CI runs the same `make check` as local. GitHub Actions, macOS + Linux matrix now; Windows is added when it becomes a goal. `uv` and ffmpeg are cached; ffmpeg is pinned.
- **Pipeline order (fail fast):** lint + types -> unit tests -> integration tests -> security (bandit, pip-audit, gitleaks, licence check) -> build wheel.
- **Branching:** trunk-based with short-lived feature branches; `main` is protected (merge only when CI is green, even when working alone). Conventional Commits drive the changelog and semantic version (`python-semantic-release` or equivalent).
- **Nightly workflow:** slow tests that are too heavy for every push: real-clip smoke test, long-film memory test, benchmarks.
- **Release workflow:** a `v*` tag runs the full suite, builds the wheel, generates the SBOM, and publishes the artifacts with a changelog. Installers (PyInstaller/Tauri, macOS notarisation) are post-MVP.
- **Dependency updates:** Dependabot/Renovate PRs, gated by the same CI.
- **Out of scope (YAGNI):** Docker, Kubernetes, microservices. A local CLI does not need them.

### Repo layout
```
src/filmanalyser/
  core/        contracts: Chunk, Extractor protocol, config, errors (pure, immutable)
  media/       ffmpeg streaming + chunker
  extractors/  registry.py + shot_cuts, color, letterbox, loudness, speech_music
  pipeline/    runner: wires extractors to chunks, storage and logging
  storage/     versioned Parquet feature store, resume manifest
  analysis/    pacing, tension, act_breaks, flags
  report/      viewmodel, renderer, templates/, resources/{strings,colors}.toml
  cli/         entry point, argument parsing, orchestration
tests/{unit,integration,architecture,fixtures}
```

### Test fixtures (no copyrighted film needed in CI)
Synthetic clips are generated deterministically with `ffmpeg -f lavfi` (testsrc, color flashes at known cut times, sine/noise/silence audio at known timestamps). Ground truth is known by construction. A real-clip smoke test runs in Phase 4 and full real-film validation happens manually in Phase 8.

### Phase Handoff Protocol (applies to every phase)
Before the next phase starts, produce `docs/handoff/phase-N.md` containing:
1. **Tech debt incurred**, listed honestly.
2. **Exact steps taken to resolve each item now.** Nothing is deferred. Unavoidable items must be recorded in `BACKLOG.md` as a decision, not as silent debt.
3. **Confirmation:** the raw `make check` output showing a green build and all tests passing.
Then pause for your approval.

---

## Phase 1: Foundation and guardrails
**Status: built and green locally; NOT closed. Two items need a GitHub remote and are tracked in "Final phase: Pending items" at the end of this file. Handoff: `docs/handoff/phase-1.md`.**

**Goal:** An empty but fully green project with every rule automated.
- **Tests first:** the architecture tests (file size, layer imports, hex/string literal bans, banned security patterns) are written first and run against a skeleton.
- **Deliver:** `pyproject.toml`, `Makefile` (`make check`), lint/type/security configs, package skeleton, resource files (`strings.toml`, `colors.toml`) with a loader and a typed accessor (`Strings`, `ColorTokens`), CI-equivalent local script, `git init` + `.pre-commit-config.yaml`, ruff complexity rules, the extractor registry skeleton (`extractors/registry.py`), `.github/workflows/ci.yml` (same `make check`, macOS + Linux matrix), branch protection on `main`, Conventional Commits config.
- **Tests first (additional):** pure-layer import test, frozen-dataclass test, registry test with a dummy extractor.
- **Exit criteria:** `make check` green locally and in CI; deliberately violating each rule (temp file) makes the build fail, proving the guards work.

## Phase 2: Core contracts and streaming decoder
**Goal:** Stream any mp4 in overlapping chunks with flat memory.
- **Tests first:**
  - Unit: chunk boundaries, overlap maths, timestamp (pts) normalisation, path validation, ffmpeg-missing error.
  - Integration: synthetic 2-min clip decodes into the expected chunk count and durations; **memory-flatness test** decodes a 10x longer synthetic clip and asserts peak RSS does not grow.
- **Deliver:** `core/` (Chunk, Extractor protocol, config, errors), `media/ffmpeg_stream.py` (argument-list subprocess, never a shell), `media/chunker.py`.
- **Security checks:** the input path is resolved and checked for existence and readability, option-injection is blocked (paths passed after `--`), and the ffmpeg stderr is bounded.
- **Exit criteria:** green build; RSS flatness verified.

## Phase 3: Storage, versioning, resumability
**Goal:** Features persist compactly; a crash mid-film resumes without re-decoding finished chunks.
- **Tests first:** schema round-trip, version mismatch rejected, append-only writes, resume after a simulated crash at chunk N, corrupted manifest handled.
- **Deliver:** `storage/schema.py` (SSOT for feature names/types/version), `storage/feature_store.py` (Parquet), resume manifest.
- **Security checks:** only Parquet via a safe reader, no pickle, atomic writes (temp file + rename), output directory confined to the chosen path.
- **Exit criteria:** green build; kill-and-resume integration test passes.

## Phase 4: Video extractors + walking skeleton
**Goal:** Shot cuts and colour/light features, plus a minimal end-to-end path (CLI, one-chart report) and a real-clip smoke test (see Improvements 2 and 3).
- **Tests first:** on synthetic clips with known cut times, shot-cut detection hits the known cuts within tolerance (precision/recall asserted); colour stats checked against known frame colours; state carried across chunk boundaries gives no duplicate or missed cut.
- **Deliver:** `extractors/shot_cuts.py`, `extractors/color.py`, plus a letterbox-crop helper (promoted from the backlog because it affects accuracy; logged in `DECISIONS.md`).
- **Deliver (additional):** `.github/workflows/nightly.yml` running the real-clip smoke test, a long-film memory test, and benchmarks.
- **Exit criteria:** green build; extractors plug into the pipeline through the `Extractor` protocol and registry only (open/closed check).

## Phase 5: Audio extractors
**Goal:** Loudness and speech/music/silence.
- **Tests first:** synthetic audio with known silence, tone, and noise segments; loudness asserted against reference values; timestamp alignment with video chunks.
- **Deliver:** `extractors/loudness.py`, `extractors/speech_music.py` (Silero VAD via ONNX Runtime; model integrity is checked by pinned SHA-256 before loading).
- **Security checks:** model file hash verified, no network download at runtime (the model is vendored or fetched once by an explicit setup command).
- **Exit criteria:** green build; combined video+audio pipeline test on the synthetic clip.

## Phase 6: Timeline analysis (the stitching)
**Goal:** Turn the feature timeline into film-level findings.
- **Tests first:** synthetic timelines with known change-points, a known peak, and known flat stretches; assert act breaks, tension peak, pacing plateaus, and flagged timestamps.
- **Deliver:** `analysis/pacing.py`, `tension.py`, `act_breaks.py`, `flags.py`; every threshold lives in `core/config.py`.
- **Exit criteria:** green build; pure functions with no I/O and no report imports (architecture test).

## Phase 7: Report (MVVM view layer)
**Goal:** A static, self-contained HTML report.
- **Tests first:** ViewModel unit tests (numbers in, display-ready structure out, still locale-neutral); renderer tests assert HTML escaping, no inline literals, only `var(--token)` colours, light and dark both defined, and no external requests (strict CSP meta tag).
- **Deliver:** `report/viewmodel.py`, `report/renderer.py` (Jinja2, autoescape on), templates, charts rendered as inline SVG (no JS dependency, no network).
- **Exit criteria:** green build; the report for the synthetic clip passes the architecture tests.

## Phase 8: CLI, hardening, validation, release
**Goal:** `filmanalyser film.mp4` works end to end and meets `ACCEPTANCE.md`.
- **Tests first:** CLI integration test (exit codes, bad paths, missing ffmpeg, resume flag), full-pipeline test on the synthetic film.
- **Deliver:** `cli/main.py`, orchestration (a thin layer that only wires components), README usage section.
- **Validation (manual, recorded in the handoff):** run on 3 familiar films plus 1 held-out film; check peak RAM (< 2 GB), runtime (< 45 min), act-break tolerance (±5 min), and the tension peak against the real climax. The kill/pivot rule from `ACCEPTANCE.md` applies.
- **Security audit:** full bandit + pip-audit run, dependency pins reviewed, manual review for command injection, path traversal, and report XSS.
- **Deliver (additional):** `.github/workflows/release.yml` (tag `v*` -> full suite -> wheel -> SBOM -> artifacts + changelog), `CHANGELOG.md` generated from Conventional Commits, Dependabot/Renovate config.
- **Exit criteria:** every box in `ACCEPTANCE.md` ticked; release workflow run succeeds on a tag; release tagged; known-limitations list written.

---

## Per-phase working loop
1. Write failing tests (unit, then integration).
2. Implement until green.
3. Run `make check` locally, including the architecture and security gates.
4. Refactor for SRP, DRY and SSOT; split any file nearing 300 lines.
5. Write the handoff note and resolve all debt.
6. Pause for approval.

## Open risks tracked through the plan
- Shot-detection robustness on fades and dissolves (Phase 4): validate on real clips in Phase 8.
- Act-break detection may not match human judgement: covered by the kill/pivot rule.
- Windows support is untested in the MVP (Mac only); the engine avoids platform-specific code so it can be added later.

---

## Improvements adopted (revision 2)
1. **`git init` in Phase 1.** The project is not yet a repo. Each phase is committed and tagged `phase-N`, so a failed phase can be rolled back cleanly.
2. **Walking skeleton in Phase 4.** A minimal CLI plus a minimal report (one chart) goes end to end as soon as the first extractor exists. Integration risk is found early, and Phase 7 becomes a polish of an existing report rather than a first build.
3. **Early real-film smoke test (Phase 4).** One real clip (~5 min, kept outside the repo, path given by an env var) is run through the pipeline to check shot detection and RAM against real footage before more extractors are built on top. Full-film validation stays in Phase 8.
4. **Property-based tests** (`hypothesis`) for the chunker and overlap maths, where edge cases cause off-by-one bugs.
5. **Determinism test:** the same input must give byte-identical feature files.
6. **Performance budget test:** a per-chunk time ceiling on the synthetic clip so slowdowns fail the build rather than appear at Phase 8.
7. **Golden-file tests** for analysis outputs, so threshold changes are visible in review.
8. **Supply-chain hygiene:** `uv.lock` with hashes, a licence check (`pip-licenses`) against an allowlist, and minimal dependencies (OpenCV headless, not full).
9. **Accessibility test:** the colour tokens in `colors.toml` are checked for WCAG AA contrast in both light and dark themes.
10. **Structured logging** with per-chunk RAM and time. Logs never contain film content; paths are logged by basename only.
11. **Error taxonomy** in `core/errors.py` (input, decode, model, storage, analysis), mapped to stable CLI exit codes.
12. **Pre-commit hooks** run the fast subset of `make check` so violations are caught before a commit.
13. **Parallelism with a RAM cap:** video and audio extraction run in separate processes with a bounded worker count. This is added only after the memory-flatness test passes, and it must keep that test green.

---

## Files created per phase
Tests are listed alongside the code they cover (written first). Every phase also creates `docs/handoff/phase-N.md`.

| Phase | Source / config files | Test files |
|---|---|---|
| **1 Foundation** | `pyproject.toml`, `uv.lock`, `Makefile`, `.pre-commit-config.yaml`, `.gitignore`, `src/filmanalyser/__init__.py`, `core/config.py`, `core/errors.py`, `report/resources/strings.toml`, `report/resources/colors.toml`, `report/resources/strings.py`, `report/resources/colors.py`, `scripts/guard_selftest.py`, `scripts/guard_probes.py`, `core/extractor.py`, `extractors/registry.py`, `report/resources/_toml.py`, `.python-version`, `.github/workflows/ci.yml`, `docs/BRANCH_PROTECTION.md`, `docs/handoff/phase-1.md`, empty layer packages (`media`, `pipeline`, `storage`, `analysis`, `cli`) | `tests/architecture/test_file_size.py`, `test_layer_imports.py`, `test_no_hardcoded_strings.py`, `test_no_hardcoded_colors.py`, `test_security_patterns.py`, `test_color_contrast.py`, `test_frozen_dataclasses.py`, `test_function_limits.py`, `test_ci_workflow.py`; `tests/unit/test_resources.py`, `test_config.py`, `test_errors.py`, `test_registry.py`; `tests/integration/test_wheel_resources.py` |
| **2 Decoder** | `core/chunk.py`, `core/extractor.py` (protocol), `media/probe.py`, `media/ffmpeg_stream.py`, `media/chunker.py`, `media/paths.py` | `tests/fixtures/make_synthetic.py`; `unit/test_chunker.py` (incl. hypothesis), `test_probe.py`, `test_paths.py`; `integration/test_decode_stream.py`, `test_memory_flat.py` |
| **3 Storage** | `storage/schema.py`, `storage/feature_store.py`, `storage/manifest.py` | `unit/test_schema.py`, `test_feature_store.py`, `test_manifest.py`; `integration/test_resume.py`, `test_determinism.py` |
| **4 Video + skeleton** | `extractors/shot_cuts.py`, `extractors/color.py`, `extractors/letterbox.py`, `pipeline/runner.py` (wires extractors per chunk), `cli/main.py` (minimal), `report/` minimal (`viewmodel.py`, `renderer.py`, one template) | `unit/test_shot_cuts.py`, `test_color.py`, `test_letterbox.py`, `test_runner.py`; `integration/test_video_pipeline.py`, `test_real_clip_smoke.py` (skipped unless the env var is set; documented in the handoff) |
| **5 Audio** | `extractors/loudness.py`, `extractors/speech_music.py`, `models/silero_vad.onnx`, `models/MANIFEST.sha256`, `scripts/fetch_models.py` | `unit/test_loudness.py`, `test_speech_music.py`, `test_model_integrity.py`; `integration/test_av_pipeline.py` |
| **6 Analysis** | `analysis/timeline.py`, `pacing.py`, `tension.py`, `act_breaks.py`, `flags.py` | `unit/test_pacing.py`, `test_tension.py`, `test_act_breaks.py`, `test_flags.py`; `tests/golden/*.json`; `integration/test_analysis_pipeline.py` |
| **7 Report** | `report/viewmodel.py` (full), `report/renderer.py`, `report/charts.py` (inline SVG), `report/templates/report.html`, `report/templates/partials/*.html` | `unit/test_viewmodel.py`, `test_charts.py`; `integration/test_report_render.py` (escaping, tokens, light/dark, no external URLs) |
| **8 CLI + release** | `cli/main.py` (full), `cli/args.py`, `docs/USAGE.md`, `docs/LIMITATIONS.md`, `scripts/validate_real_film.py` | `integration/test_cli.py`, `test_full_pipeline.py`, `test_exit_codes.py` |

Any file that approaches 300 lines is split before the phase closes; the only exceptions carry an `# SRP-EXCEPTION:` comment explaining why.

---

## Final phase: Pending items
Anything unfinished in an earlier phase is consolidated here. A phase listed below is not complete until its items are done. Nothing is hidden as silent debt.

| # | From | Pending item | Why it is pending | How to close it |
|---|------|--------------|-------------------|-----------------|
| P1-1 | Phase 1 | **CI has never run.** `.github/workflows/ci.yml` is written and structurally tested, but the exit criterion "`make check` green ... in CI" is unverified | The repository has no GitHub remote yet; creating one is an outward-facing action that needs your approval | Follow `docs/BRANCH_PROTECTION.md` steps 1-2; confirm `ci` is green on macos-latest and ubuntu-latest; fix anything that differs from local |
| P1-2 | Phase 1 | **Branch protection on `main` is not applied** (instructions are written) | Needs the remote from P1-1, and a GitHub plan that supports protection on private repos | `docs/BRANCH_PROTECTION.md` steps 3-4, then verify a direct push is rejected |

Phase 1 is complete only when P1-1 and P1-2 are ticked.
