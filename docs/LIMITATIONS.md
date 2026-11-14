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

- **Speech under music is missed, and neither threshold changes nor YAMNet fix it** (YAMNet raises
  speech-under-music recall from 37% to 42%, DECISIONS #85). A lower voice threshold (0.1) recovers only
  about 8 points of recall and costs about 7 points of precision; a syllable-rate cue does not separate
  speech under music from tonal music (DECISIONS #81). The remaining options are a different voice
  model or source separation, which need a decision.
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

## Alignment and sync

- **Sound and picture are aligned on the container clock** (DECISIONS #67), with a silent lead when
  the track starts late. Alignment has been checked only on synthetic clips with a known offset and
  on the local films; no film with a known sync event (such as a clap) has been checked.

## Scope

- **Not a quality score.** The features describe craft (pacing, colour, sound), not whether a film is
  good (DECISIONS #6).
- **The evidence comes from a small set of films.** The local films, eight AVA clips, and a stitched
  film made from real footage. Full validation on films the owner knows is still to be done.
