# Decisions

Append-only. To change a decision, add a new entry that supersedes the old one; do not edit past entries.

| # | Date | Decision | Why |
|---|------|----------|-----|
| 1 | 2026-11-11 | Local-first app, not a hosted website | Films are 2-8 GB and private; compute is light enough locally |
| 2 | 2026-11-11 | Stream video in chunks; keep only compact features | Constant RAM regardless of film length |
| 3 | 2026-11-11 | Classical/tiny extractors, no large VLM | Low RAM and compute; LLM captions are unreliable for craft analysis |
| 4 | 2026-11-11 | Python engine + ffmpeg; ONNX Runtime for any models | Best ecosystem; runs on Mac (CoreML) and Windows (DirectML) |
| 5 | 2026-11-11 | MVP is CLI + static HTML report | Analysis quality is the hard part; UI comes after it is proven |
| 6 | 2026-11-11 | Output is relative, genre-aware craft metrics, not absolute quality scores | No objective ground truth for film quality |
| 7 | 2026-11-11 | Feature files are versioned (Parquet metadata) | Avoid silently mixing outputs from different extractor versions |
| 8 | 2026-11-11 | MVVM mapping: Model = core/storage/analysis, ViewModel = report/viewmodel.py, View = templates + CLI renderer | Applies MVVM to a CLI + report app without a GUI framework |
| 9 | 2026-11-11 | "Build" = `make check` (ruff, mypy --strict, pytest, bandit, pip-audit, wheel build) | Gives every phase a single objective pass/fail |
| 10 | 2026-11-11 | Architecture rules (300 LOC, layer imports, no hardcoded strings/colours, banned security patterns) are enforced by tests | Rules that are not automated drift |
| 11 | 2026-11-11 | CI fixtures are synthetic ffmpeg-generated clips with known ground truth | Fast, deterministic, no copyrighted film in the repo |
| 12 | 2026-11-11 | Charts are inline SVG; report has no JS and no network requests | Security and portability |
| 13 | 2026-11-11 | Letterbox cropping promoted from backlog into Phase 4 | It affects colour and framing accuracy |
| 14 | 2026-11-11 | `git init` in Phase 1; each phase committed and tagged `phase-N` | Clean rollback of a failed phase |
| 15 | 2026-11-11 | Walking skeleton (minimal CLI + one-chart report) and real-clip smoke test move into Phase 4 | Find integration and real-footage problems early |
| 16 | 2026-11-11 | KISS, YAGNI and rule of three; complexity limits enforced by ruff (complexity <= 10, function <= 40 lines, <= 5 args) | Keeps code simple; the 300-line file cap alone does not limit function complexity |
| 17 | 2026-11-11 | Pure core, thin shell: `core/` and `analysis/` are pure and use frozen dataclasses; I/O only in `media/`, `storage/`, `pipeline/`, `cli/` | Testability and safe parallelism |
| 18 | 2026-11-11 | Extractors are added through a registry (open/closed); schema and extractor protocol are versioned public contracts | Scale by adding modules, not editing existing ones |
| 19 | 2026-11-11 | Stages are idempotent and cached by input hash + feature version | Cheap re-runs and batch/corpus processing later |
| 20 | 2026-11-11 | CI = the same `make check` on GitHub Actions (macOS + Linux); `main` protected; trunk-based flow with Conventional Commits | One definition of green; automatic changelog and versioning |
| 21 | 2026-11-11 | Nightly workflow for slow tests; tag-triggered release workflow builds wheel, SBOM, changelog | Keep push CI fast while still covering heavy checks |
| 22 | 2026-11-11 | Supply-chain controls: hashed lockfile, gitleaks, pip-audit, licence allowlist, Dependabot/Renovate | Security rule requires it on every addition |
| 23 | 2026-11-11 | No Docker, Kubernetes or microservices | YAGNI: a local CLI does not need them |
