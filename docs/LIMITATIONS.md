# Known limitations

The measured limits of the analysis, with the evidence for each. Every number here comes from a run
recorded in `DECISIONS.md` or `docs/handoff/`. A limitation is not a defect to hide: it is what the
output can and cannot be trusted for.

## Shots and cuts

- **Hard cuts.** On the stitched film of real shots, with all 18 cuts verified on the detector's own
  frame pairs, precision and recall are both 100% at 0.25 s, and 78% at one analysis frame (0.08 s);
  cut timing is reliable to a quarter of a second (DECISIONS #83). On a fresh ten minutes of The
  Odyssey, every one of 83 small-change cuts was found. Effects-heavy footage still produces some false
  cuts: on Tears of Steel, 5 of 35 effect changes (holograms, explosions, fast motion) pass the rule.
- **Gradual transitions.** Dissolves and fades are found when the frames are a real blend of the two
  pictures (DECISIONS #84). On Tears of Steel, 4 transitions are reported in 12 minutes: two fades and
  two on-screen hologram dissolves; camera moves, flashes and effects are rejected. A transition that
  is not a blend (a wipe, a whip pan) is not reported. Evidence for gradual transitions comes from
  synthetic clips and one film; no labelled set of real dissolves has been measured.

## Speech, music and silence

- **Speech under music depends on the soundtrack format.** For a 5.1 track the voice detector hears
  the centre channel, where dialogue is mixed: on Tears of Steel, speech recall is 59% with 0.2%
  false speech (it was 33% on the averaged mix; DECISIONS #86). For a stereo or mono track there is no
  dialogue channel: speech under loud music or effects is found about a third of the time (32% on
  Tears of Steel stereo). The opt-in `--separate-voices` mode separates the voice (Demucs) on chunks
  whose background is loud: overall speech recall on Tears of Steel stereo goes from 49% to 59%, and
  on the AVA clips from 56% to 68% (DECISIONS #88). Its costs: it needs the `demucs` tool (PyTorch)
  and an 84 MB model, about 8 times real time on an Apple M4 GPU (much slower on CPU only), and it
  reads singing as speech (false speech 2.2% to 5.4% on AVA; 16% on a clip of sustained singing).
  Without it, threshold changes and YAMNet were measured and do not fix this (DECISIONS #81, #85).
- **Speech under music is missed (measured).** On eight hand-labelled AVA-Speech clips (5 minutes each, 37,447
  labelled-speech windows pooled), speech over background music is found 29% of the time; clean speech
  80%; speech with noise 57% (DECISIONS #77). Silero reads speech under music as non-speech, and the classifier then labels it
  tonal. The feature is therefore `tonal_ratio` (DECISIONS #75), not "music".
- **Speech precision is high, recall is moderate.** Pooled over the eight clips: precision 96.4%,
  recall 56.1%, and no-speech windows read as speech 2.2% of the time (DECISIONS #77). Recall varies
  widely by clip (33% to 81%). The clips are from eight different videos, not from films the owner knows.
- **Silence is a level, not a judgement.** A window below -50 dBFS counts as silence, so any audio
  below -50 dBFS counts as silence, whatever it contains.

## Loudness

- **Measured at 48 kHz (BS.1770's rate); the reference is ffmpeg's `ebur128`.** On three full films
  (80 s stereo, 12 min stereo, 2 h 52 min 5.1) integrated loudness and true peak agree with
  `ebur128` within 0.05 (DECISIONS #74). That reference is an independent implementation, not an
  EBU-accredited meter.
- **Channel weights:** 5.1 uses the BS.1770 weights (LFE excluded, surrounds 1.41). Other layouts
  weight every channel equally. Layouts beyond 5.1 are downmixed by ffmpeg before measurement.
- **True peak is 4x oversampled.** It agrees with the EBU Table 1 signals within 0.03 dB (DECISIONS
  #71). A peak in the last 1 ms of a window is not counted (the window end has no following samples).
- **Peaks above full scale happen.** Decoded float audio can exceed 0 dBFS, so `peak_dbfs` and
  `true_peak_dbfs` can read above zero. This is the audio, not an error (DECISIONS #69).
- **A tone that stops abruptly rings for about 50 ms** in the K-weighting filter, and BS.1770 counts
  that block. A silent passage right after an abrupt stop can read well above the -70 LUFS floor.

## Timeline analysis (act breaks, tension, pacing, flags)

Evidence is synthetic timelines and four local films; see DECISIONS #90 to #92. None of these
results has been checked against anything a person has judged.

- **No ground truth for act structure.** No film in this repository has labelled act breaks. What is
  tested is that the rules find the change points built into constructed timelines, and not noise.
  Whether a reported break is an act break is not known, and the output must be read as "where the
  film's picture and sound changed most", not as acts.
- **Thresholds calibrated on synthetic data only.** `ACT_MIN_SCORE` (1.5) and `TENSION_MIN_PEAK_Z`
  (3.0) were set from noise films and single steps (largest noise score 1.36 over 2,400 films, a step
  1.9 or more; largest noise tension 2.75). Not calibrated on real footage: real features are
  correlated and heavy-tailed, so noise-level scores on a film may be higher than on the synthetic
  noise. The other thresholds (pacing plateau, flag limits, zones, window, smoothing, merge gap) are
  chosen by reasoning and tested on constructed cases; none was tuned on real footage.
- **Real-film result: no break found.** On The Odyssey (2 h 52 min, 5.1, 173 chunks) the strongest
  candidate in zone 1 scored 1.15 (at 0:31, 18%) and in zone 2 1.27 (at 2:21, 82%), both below the
  threshold and inside the range noise reaches, so no break is reported. The threshold was not lowered
  to produce one. Whether the film has no break in these zones, or has breaks the features cannot see,
  is not known.
- **Short films cannot be scored at the default chunk size.** A boundary needs 5 chunks on each side,
  so a film under 10 minutes has no score at all, and a break needs a 10-minute gap. The two Tears of
  Steel files (12 min, 12 chunks) score 3 boundaries and no break; the 80 s stitched film has 2
  chunks and none. At 10 s chunks (73 chunks) Tears of Steel gives no break either: the best
  candidates inside the zones score 1.05 (zone 1, at 3:00) and 0.84 (zone 2, at 10:30) for stereo, and
  within 0.05 of those for 5.1. The strongest candidate overall (1.27 at 1:00, 8%) lies outside both
  zones. The window is then 50 s, not 5 min, so this is an exploration, not the specified analysis.
- **A change in a minority of features scores low.** The score divides by the square root of the
  number of features, so a step in one feature of nine scores 0.63, and a film that climbs in equal
  stages (steps of 0, 3, 6) scores each stage 1.23, below the threshold. Both are kept by design
  and tested. A break needs several features to move together relative to the film's own spread.
- **Film-relative, so a film with no structure is stretched.** Z-scores use the film's own mean and
  spread; a nearly constant feature still fills the unit scale. The threshold is what stops noise
  from becoming a break.
- **A film without audio is analysed on the picture alone** (cut rate and four colour features) and
  says so (`audio_used`). The letterbox share is not used. Loudness at the -70 LUFS floor counts as
  missing, so a silent stretch is invisible in loudness (it still shows in the silence share).
- **Tension is cut rate and loudness only** (a mean of their z-scores). It is a proxy that follows
  how fast and how loud a film is, not what happens. On The Odyssey the peak is at 1:51 (z 3.5), the
  same minute as the strongest fast-cutting flag; this is an observation, not a check against the
  film's climax, which Phase 8 does.
- **Pacing plateaus are relative to the film's spread.** A few huge bursts widen the band, so a
  plateau can run a chunk into its neighbours. The Odyssey has 4 (the last, 2:46 to the end at 0 cuts
  per minute, is the end credits).
- **Flags are rules, not findings.** `clipping` is a true peak at or above 0 dBTP (8 chunks on The
  Odyssey, peaks of +0.06 to +1.06 dBTP); `quiet` is a share of windows below -50 dBFS; `long_take` is three
  chunks in a row without a cut or transition (so credits and static title cards are flagged).

## Alignment and sync

- **Sound and picture are aligned on the container clock** (DECISIONS #67), with a silent lead when
  the track starts late. Alignment has been checked only on synthetic clips with a known offset and
  on the local films; no film with a known sync event (such as a clap) has been checked.

## Scope

- **Not a quality score.** The features describe craft (pacing, colour, sound), not whether a film is
  good (DECISIONS #6).
- **The evidence comes from a small set of films.** The local films, eight AVA clips, and a stitched
  film made from real footage. Full validation on films the owner knows is still to be done.
