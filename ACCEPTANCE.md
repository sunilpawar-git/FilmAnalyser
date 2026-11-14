# MVP Acceptance Checklist

The MVP is done only when every item is checked, on a film **not used during development**.

## Performance
- [x] Peak RAM < 2 GB on a 3 hr film (The Odyssey, 2:52 5.1: 1505 MB after the fix, DECISIONS #99, #103)
- [x] Memory-flatness test passes (peak RAM does not grow with film length)
- [x] Full run < 45 min on the dev Mac (record chip + RAM: Apple M4, 16 GB; The Odyssey 12:10)
- [x] Run is resumable after a crash mid-film (`test_resume.py`, `test_resume_grid.py`, real footage; DECISIONS #54)

## Output
- [ ] Report contains all MVP metrics (all but the colour palette: P7-1): shot cuts / average shot length, cut-rate curve, colour palette and brightness, loudness profile, speech/music/silence ratio, tension curve, act breaks, flagged timestamps
- [x] Every flagged issue carries a timestamp (`test_full_pipeline.py`)
- [x] Features are stored in versioned Parquet; re-analysis does not re-decode the film (`test_full_pipeline.py`)

## Validity (on 3 films you know well)
- [ ] Detected act breaks fall within ±5 min of the real ones (tolerance editable here: ____)
- [ ] Tension curve peaks near the actual climax
- [ ] Shot-cut detection spot-checked against hand-labelled 2-min clips (measured on real footage with frame-pair labels by the assistant, DECISIONS #83; not the owner's hand labels)

Kill/pivot rule: if act-break detection misses on 2 of 3 films after a 3-day time-box, change the approach rather than keep tuning.

## Quality gates
- [x] Unit test per extractor
- [x] Golden-output test on the short clip (`test_golden_clip.py`, DECISIONS #100)
- [x] Known-limitations list written (`docs/LIMITATIONS.md`)
- [ ] Feature schema version frozen and tagged (frozen: `test_schema_frozen.py`; the tag is made with the release tag, P8-2)

## Release
- [ ] All items above checked on a held-out film
- [ ] Release tagged
