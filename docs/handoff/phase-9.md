# Phase 9 handoff: what is still open after Phase 8

**PHASE 8 IS STILL NOT COMPLETE.** This branch (`feat/p7-1-colour-palette`) closes P7-1 only. P8-1, P8-2, P6-1 and P6-2 are open because they need the owner. Nothing was estimated or invented in their place (DECISIONS #94).

## Done here
- **P7-1 (owner chose: build the palette).** `color` extractor v2 stores three dominant colours per chunk (`extractors/palette.py`); the report shows a strip and the film's top five (`report/palette_view.py`). DECISIONS #106. The frozen schema file and the golden clip were refreshed on purpose. Every store made before this is unreadable and is re-extracted on the next run.
- Palette cost measured: 0.03 s per 60 s chunk (160 x 90) on top of 0.23 s for the rest of the extractor.
- Not done for the palette: it has not been looked at on a real film, in a browser, light or dark (the browser tool was busy). Its HTML was inspected on a rendered synthetic clip only.

## Update 2026-11-16: validation without owner truth (DECISIONS #107)
The owner has no times or labels to give and asked for published material. Searches found no published act-break times for any of the five films. Climax scenes named by plot summaries were located in the files on frame sheets (Kill Bill 1 about 1:36:45, Kill Bill 2 about 1:59:40, Moonrise Kingdom about 1:21:40; not owner-verified). Fresh runs: peak RAM about 1.0 GB, run time 3:26 to 4:19, all within budget. No act breaks and no tension peak above threshold in any of the three; the highest tension value was near the climax in Moonrise only (1 of 3). Nothing was ticked in ACCEPTANCE. Raw table:
```
| Kill Bill Vol. 1 | 1:50:43 | 1024 MB (yes) | 3:26 (yes) | none | 0/0 (n/a) | none (n/a) |
| Kill Bill Vol. 2 | 2:16:57 | 1020 MB (yes) | 4:19 (yes) | none | 0/0 (n/a) | none (n/a) |
| Moonrise Kingdom | 1:33:38 | 1013 MB (yes) | 3:28 (yes) | none | 0/0 (n/a) | none (n/a) |
```
The act-break and kill/pivot checks need act times nobody has published; the shot-cut spot check needs labels. These remain open unless the owner supplies or approves a different truth source.

## Update 2026-11-16 (2): claims reworded, reports viewed (DECISIONS #108)
PR #23 was merged (rebase). The 1:20:00 coincidence is real action in both Kill Bill films, not an artefact. The report now says 'largest shifts' and 'intensity' and states the measured result; the two ACCEPTANCE Validity boxes stay unticked as failed. The palette is mostly near-black (LIMITATIONS). Shot-cut check on a public dataset: in progress, see DECISIONS when done.

## Still open, with the exact steps
1. **P8-1 needs from the owner:** paths of 3 familiar films and 1 held-out film; their verified act-break times and climax time for each; hand-labelled shot cuts for a short clip. Write the truth JSON in the `docs/USAGE.md` format with `"verified_by": "owner"`.
2. Run `scripts/validate_real_film.py` on the four films (it re-extracts every store, because of the palette). Check: peak RAM < 2 GB, run time < 45 min, act breaks within 5 min, tension peak near the real climax. Apply the kill/pivot rule of `ACCEPTANCE.md`. Calibrate `ACT_MIN_SCORE` on the 3 films and test on the held-out one.
3. Open each film's report at full length in light and dark (P7-2), including the palette section. Run the shot-cut spot check against the owner's labels.
4. Tick ACCEPTANCE boxes only with that evidence: act breaks within 5 min, tension near the climax, shot-cut spot check, all items on a held-out film. Close P6-1 and P6-2. Record failures in `docs/LIMITATIONS.md` and `DECISIONS.md`.
5. **P8-2 after the owner agrees to a tag:** bump `version` in `pyproject.toml`, `make changelog`, tag `vX.Y.Z` and the schema tag (`schema-` plus the first 12 characters of the version in `tests/golden/feature_schema.json`), push, watch `release.yml`, fix what breaks, record the first run in `docs/RELEASING.md`. The schema version changed in this branch, so the schema tag must use the new one.

## Gaps against the Phase 8 plan and ACCEPTANCE (unticked boxes)
- Detected act breaks within +/-5 min of the real ones: open (no truth data).
- Tension curve peaks near the real climax: open (no truth data).
- Shot-cut spot check against the owner's hand labels: open (the existing check is the assistant's own frame-pair labels, DECISIONS #83).
- Feature schema frozen and tagged: frozen, tag not made (P8-2).
- All items checked on a held-out film: open.
- Release tagged: open; `release.yml` has never run on a tag.

## `make check` on this branch (raw lines kept from the log)
```
uv run --locked ruff check .
All checks passed!
uv run --locked ruff format --check .
uv run --locked mypy
uv run --locked pytest tests/unit tests/architecture tests/integration -m "not real_clip and not slow and not separation"
============================= test session starts ==============================
================================ tests coverage ================================
TOTAL    2703      0    486      0   100%
Required test coverage of 90% reached. Total coverage: 100.00%
================ 1138 passed, 7 deselected in 74.70s (0:01:14) =================
uv run --locked pip-audit --require-hashes --disable-pip -r .cache/audit-requirements.txt
uv run --locked pip-licenses --allow-only="MIT License;MIT;BSD License;3-Clause BSD License;BSD-2-Clause;BSD-3-Clause;Apache Software License;Apache-2.0;Apache-2.0 OR BSD-2-Clause;Python Software Foundation License;PSF-2.0;ISC License (ISCL);MPL-2.0;Mozilla Public License 2.0 (MPL 2.0);The Unlicense (Unlicense);0BSD;BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0" --format=plain >/dev/null
uv run --locked bandit -q -r src scripts -c pyproject.toml
Successfully built dist/filmanalyser-0.1.0-py3-none-any.whl
uv run --locked python scripts/guard_selftest.py
guard self-test: 0 failing guard(s)
```
