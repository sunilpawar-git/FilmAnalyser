# MVP Acceptance Checklist

The MVP is done only when every item is checked, on a film **not used during development**.

## Performance
- [ ] Peak RAM < 2 GB on a 3 hr film
- [ ] Memory-flatness test passes (peak RAM does not grow with film length)
- [ ] Full run < 45 min on the dev Mac (record chip + RAM: ____)
- [ ] Run is resumable after a crash mid-film

## Output
- [ ] Report contains all MVP metrics: shot cuts / average shot length, cut-rate curve, colour palette and brightness, loudness profile, speech/music/silence ratio, tension curve, act breaks, flagged timestamps
- [ ] Every flagged issue carries a timestamp
- [ ] Features are stored in versioned Parquet; re-analysis does not re-decode the film

## Validity (on 3 films you know well)
- [ ] Detected act breaks fall within ±5 min of the real ones (tolerance editable here: ____)
- [ ] Tension curve peaks near the actual climax
- [ ] Shot-cut detection spot-checked against hand-labelled 2-min clips

Kill/pivot rule: if act-break detection misses on 2 of 3 films after a 3-day time-box, change the approach rather than keep tuning.

## Quality gates
- [ ] Unit test per extractor
- [ ] Golden-output test on the short clip
- [ ] Known-limitations list written
- [ ] Feature schema version frozen and tagged

## Release
- [ ] All items above checked on a held-out film
- [ ] Release tagged
