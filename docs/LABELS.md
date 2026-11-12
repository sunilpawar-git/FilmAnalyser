# Hand labels for real footage

Used by `scripts/evaluate_labels.py` to measure what the analysis cannot measure on its own: speech
and music accuracy (P5-1, P5-2), cut accuracy (P4-4) and full-film loudness (P5-3). The films stay
on your machine; only the label files and the numbers below are needed.

## The label file

One plain-text file per film, named `<film>.labels`, in this format. Lines starting with `#` are
comments. Times are seconds from the start of the film, as decimals (`83.25`).

```
# IMG_0309.MOV, labelled by hand
speech 12.0 15.5        # a span: someone talks (dialogue, narration, speech over music counts)
speech 40.2 44.9
music 0 79.7            # a span: music is the main sound; background music under speech is not music
silence 60.0 61.0       # a span: no audible sound
cut 31.04               # a hard cut: the frame where a new shot starts
cut 58.20
```

Rules:
- Label only what you are sure of. Parts you leave unlabelled are ignored, not counted as wrong.
- Spans of the same kind may not overlap. `speech` and `music` may overlap (speech over music).
- A cut is the first frame of the new shot. Give it to about 0.1 s.
- Fades and dissolves are not hard cuts: do not label them as `cut`.

## Full-film loudness (optional, for P5-3)

Run this on each film and keep the printed numbers:

```
ffmpeg -nostats -hide_banner -i FILM -map 0:a:0 -af ebur128=peak=true -f null - 2>&1 | tail -14
```

Copy the `I:` (integrated) and the `Peak:` under `True peak` into the label file:

```
ebur128_integrated -34.0
ebur128_true_peak -0.3
```

## What to send

For three films: the `.labels` file for each, and the two `ebur128_*` lines. The films themselves
are not needed. If you prefer to keep the films private, you can run the evaluator locally:

```
uv run --locked python scripts/evaluate_labels.py FILM FILM.labels
```

It prints precision and recall for speech, music and cuts, and the loudness gap.
