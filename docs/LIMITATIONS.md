# Known limitations

The measured limits of the analysis, with the evidence for each. Every number here comes from a run
recorded in `DECISIONS.md` or `docs/handoff/`. A limitation is not a defect to hide: it is what the
output can and cannot be trusted for.

## Shots and cuts

- **Hard cuts only.** Fades and dissolves are not detected (P4-3). The shot detector compares
  colour histograms of consecutive frames, which catches a cut but not a transition spread over
  many frames. A gradual transition is therefore reported as no cut at all. Evidence: the synthetic
  cut tests have no gradual transitions; the stitched real-footage film (below) has none either.
  Remedy, if wanted: a dissolve/fade detector with its own synthetic ground truth (a new decision).
- **Precision on real footage is low.** On a stitched film of eight real 10-second shots with seven
  known hard cuts (from IMG_0309, Tears of Steel, The Odyssey and two AVA clips; ground truth exact), with a tolerance of
  0.25 s the detector gives recall 86% (6 of 7) and precision 54% (7 false cuts among 13 reported).
  Five of the seven false cuts fall inside one AVA clip and two inside one film shot; none sit at a join,
  but the cause (motion, compression or flashes) was not inspected. At the
  tightest tolerance (one analysis frame, 0.08 s) precision is 23% and recall 43%. Cut timing is
  therefore reliable only to about a quarter of a second, and the cut-rate curve over-counts on
  busy footage. Measured on DECISIONS #76.
- **Some joins are missed.** The join at 49.9 s (Tears of Steel into an AVA clip) was not found; the
  cause was not inspected.
- **Cut-rate and average shot length are as good as the cut count**, so they carry the same
  over-counting on busy footage.

## Speech, music and silence

- **Speech under music is missed.** On eight hand-labelled AVA-Speech clips (5 minutes each, 37,447
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
