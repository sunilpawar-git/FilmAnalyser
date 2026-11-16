# MVP Acceptance Checklist

The MVP is done only when every item is checked, on a film **not used during development**.

## Performance
- [x] Peak RAM < 2 GB on a 3 hr film (The Odyssey, 2:52 5.1: 1505 MB after the fix, DECISIONS #99, #103)
- [x] Memory-flatness test passes (peak RAM does not grow with film length)
- [x] Full run < 45 min on the dev Mac (record chip + RAM: Apple M4, 16 GB; The Odyssey 12:10)
- [x] Run is resumable after a crash mid-film (`test_resume.py`, `test_resume_grid.py`, real footage; DECISIONS #54)

## Output
- [x] Report contains all MVP metrics (the colour palette is `color` v2, DECISIONS #106; `test_report_render.py`): shot cuts / average shot length, cut-rate curve, colour palette and brightness, loudness profile, speech/music/silence ratio, tension curve, act breaks, flagged timestamps
- [x] Every flagged issue carries a timestamp (`test_full_pipeline.py`)
- [x] Features are stored in versioned Parquet; re-analysis does not re-decode the film (`test_full_pipeline.py`)

## Validity (on 3 films you know well)
- [ ] Detected act breaks fall within ±5 min of the real ones (tolerance editable here: ____) — **failed on the evidence available, no longer claimed:** 0 of 7 found (DECISIONS #94), nothing above threshold on 3 more films (#107); the report now says 'largest shifts' (#108)
- [ ] Tension curve peaks near the actual climax — **failed on the evidence available, no longer claimed:** 1 of 3 films with climaxes located from plot summaries (#107); the report now calls it intensity (#108)
- [x] Shot-cut detection spot-checked against labelled footage: public BBC Planet Earth episode 10 (49 min, CC-BY-4.0, labels by the dataset's authors): precision 82.9%, recall 81.2% of 341 cuts at 0.25 s (DECISIONS #109); earlier frame-pair labels by the assistant, #83. Not the owner's hand labels and not 2-minute clips

Kill/pivot rule: if act-break detection misses on 2 of 3 films after a 3-day time-box, change the approach rather than keep tuning.

## Quality gates
- [x] Unit test per extractor
- [x] Golden-output test on the short clip (`test_golden_clip.py`, DECISIONS #100)
- [x] Known-limitations list written (`docs/LIMITATIONS.md`)
- [ ] Feature schema version frozen and tagged (frozen: `test_schema_frozen.py`; the tag is made with the release tag, P8-2)

## Release
- [ ] All items above checked on a held-out film
- [ ] Release tagged
