# Phase 5 handoff: Audio extractors (loudness, speech/music/silence)

**Status: built on `feat/phase-5-audio`, awaiting your approval before merge.** `make check` exits 0 on this tree (602 passed, 6 deselected, coverage 100%). Real-footage checks pass on `IMG_0309.MOV` (local). Five items are open and consolidated as P5-1 to P5-5 in `EXECUTION_PLAN.md`.

## What was built

- **Audio on the chunk** (`core/chunk.py`): `Audio` is a frozen, read-only value (16 kHz, mono or stereo float32, the same window as the chunk's frames including the overlap, and optional per-window `voice` probabilities). `Chunk.audio` is optional, so video-only code is unchanged. `core_audio` and `audio_core_offset` give the core window's samples.
- **Audio decoding** (`media/audio.py`): ffprobe gives the channel count (`audio_channels`); one ffmpeg process per chunk window (`decode_window`, `attach_audio`). Stateless, so a resumed run gets the same audio. A track that ends early reads as silence after its end, so every window keeps its exact length.
- **Voice detection** (`media/vad.py`): Silero VAD v6.2.3 through ONNX Runtime 1.31.1. The model is verified against `MANIFEST.sha256` before any byte reaches the runtime (`read_verified`). `VoiceDetector.probabilities` runs the v5+ layout (512-sample windows, 64-sample context, recurrent state). `attach_voice` adds the probabilities to each chunk.
- **Loudness** (`extractors/loudness.py`, `extractors/_kweighting.py`): BS.1770-4 K-weighting derived for 16 kHz, gated integrated loudness per chunk core, and the sample peak (`peak_dbfs`, not true peak). Features: `integrated_lufs`, `peak_dbfs`.
- **Speech, music, silence** (`extractors/speech_music.py`): each 32 ms window is labelled silence, speech (voice probability at least 0.5), music (non-speech and tonal, spectral flatness below 0.2) or other. Features: `silence_ratio`, `speech_ratio`, `music_ratio`, `other_ratio` (they sum to 1).
- **Extractor contract and runner**: `Extractor.needs_audio` (protocol member). `pipeline/runner.py` gains `select_extractors` (a film without audio drops the audio extractors, logged) and `chunk_stream` (decodes audio and runs the voice model when an audio extractor is kept). The registry is unchanged.
- **Model delivery**: `src/filmanalyser/models/` holds `silero_vad.onnx` (2.3 MB, MIT, licence file alongside) and `MANIFEST.sha256`. `make models` (`scripts/fetch_models.py`) is the only network path: curl over HTTPS only, size and time bounded, verified before it replaces anything. It was run in this session and installed the model with the pinned hash.
- **Dependencies**: `onnxruntime==1.31.1` (MIT, in `uv.lock`). Its transitive `protobuf` reports the licence name "3-Clause BSD License": added to the allowlist (DECISIONS #59).
- **Config** (`core/config.py`): `AUDIO_RATE`, `VOICE_WINDOW`, `VOICE_CONTEXT`, `SPEECH_PROB`, `SILENCE_DBFS`, `MUSIC_FLATNESS`, `LOUDNESS_*`, `PEAK_FLOOR_DBFS`, `AUDIO_TIMEOUT_S`, `MODEL_MAX_BYTES`, `AUDIO_MAX_CHANNELS`.
- **Errors**: new message key `error.decode.audio_failed` (strings.toml). Model failures use `error.model.default` (exit 4).

## Design choices (full text in DECISIONS #59 to #66)
- Audio is decoded per chunk, not as one stream (#60). Stereo is kept, so BS.1770's channel sum is exact for stereo films.
- Loudness runs at 16 kHz, not 48 kHz (#61). The 48 kHz coefficients are reproduced to 1e-9 (tested). Peak is labelled sample peak.
- The model lives in the package, not in a repository-root `models/` as EXECUTION_PLAN lists (#62), so the installed wheel finds it.
- A film without audio stores video features only (#64). Phase 4 stores therefore need a re-run (schema mismatch is reported, not mixed).

## 1. Tech debt incurred and found, and 2. exact steps taken to resolve each item

| # | Debt (found during the phase) | Resolution (done, verified in `make check`) |
|---|---|---|
| 1 | The licence check failed on `protobuf` ("3-Clause BSD License" not in the allowlist) | Added the name to `LICENSE_ALLOW` in the Makefile; recorded as DECISIONS #59 (same licence, not a wider rule) |
| 2 | My first loudness references assumed K-weighting is unity at 1 kHz. The implementation was right: K is +0.698 dB at 1 kHz and +0.09 dB at 440 Hz | References now come from the standard's own 48 kHz coefficients, at the tone's frequency (`test_loudness.py`, `test_av_pipeline.py`); DECISIONS #66 |
| 3 | A test helper (`_gain_db`) read the module's 16 kHz rate for a 48 kHz check, so the reference was evaluated at the wrong rate | The rate is now an argument (`test_loudness.py`) |
| 4 | A measured transient: a tone that stops abruptly leaves about 50 ms of K-filter ring-out, which BS.1770 counts; a silent core starting at the stop reads -46.7 LUFS, not the floor | Verified with decay measurements (rms 4e-2 at the stop, 2e-6 at 50 ms, float noise after 100 ms). Asserted as the expected behaviour (`test_av_pipeline.py`); DECISIONS #66 |
| 5 | `decode_argv` had six arguments (PLR0913) and a `rate` nobody varied | Dropped the parameter; the rate is `AUDIO_RATE` (`media/audio.py`) |
| 6 | A readability defect in the duration check (`math.isfinite(duration_s) > 0`, a bool compared with 0). It worked, but misleadingly | Rewritten as separate, explicit checks; covered by `test_audio_argv.py` |
| 7 | A stray duplicate import line (from an in-place edit of `runner.py`) | Merged into one `collections.abc` import |
| 8 | Inline imports in two test modules and an unused placeholder constant | Moved to module level and removed |
| 9 | `scripts/__init__.py` would have made the existing guard scripts (which import each other by file name) fail under mypy | Reverted. Tests import `fetch_models` by file name, with `scripts` added to pytest `pythonpath` (one module name, no duplicate) |
| 10 | Two existing tests assumed every film has the same extractors: the cut clip (no audio) in `test_video_pipeline.py`, the registry name list and the budget test (video-only chunks) | Updated to the stated design: audio extractors are dropped for a film without audio; the budget test now times the chunks a real run extracts, audio and voice included (`test_extract_budget.py`) |
| 11 | Branch coverage gaps (timeouts, non-zero exits, a malformed probe, the oversize model, the no-audio guards, the padding path) | Tests added for each branch; coverage is 100% (`test_audio_argv.py`, `test_audio_chunk.py`, `test_model_integrity.py`, `test_audio_decode.py`) |
| 12 | `vad.py` converts any onnxruntime failure into `ModelError` with a broad `except Exception` | Kept on purpose: onnxruntime raises several types for a malformed model. Tested with bytes that are not a model (`test_model_integrity.py`) |
| 13 | The ruff and mypy findings during the build (line lengths, import order, Yoda comparisons, numpy typing in the real-clip test) | Fixed; `ruff check`, `ruff format --check` and `mypy --strict` are clean |
| 14 | The `models/` location (plan) versus the package (needed by the installed wheel) | Recorded as DECISIONS #62; the wheel test asserts the model, manifest and licence are in the wheel (`test_wheel_resources.py`) |
| 15 | Model fetch logic untested because it is network code | The refusal and argv logic are tested without the network (`test_model_fetch.py`); `make models` was run once for real: download, verify, install, same hash |
| 16 | The nightly real-clip job did not check audio | `test_real_clip_audio_features_are_well_formed` asserts finite loudness in range, peaks at most 0 dBFS, and ratios summing to 1; it passes locally (below) |
| 17 | CI (Ubuntu, ffmpeg 6.0.1) failed 10 tests: the MP4 muxer rejects `pcm_s16le` ("Could not find tag for codec pcm_s16le"). Local ffmpeg 9.0.2 accepts it, so the local build passed | The synthetic audio track is written as QuickTime (`-f mov`, the name stays `.mp4`), which carries PCM on every ffmpeg version (`tests/fixtures/make_synthetic.py::av_clip_argv`). The non-clip tests (onnxruntime, the VAD) already passed on Linux |

No other tech debt was found. Nothing is hidden: the open items are in the table below.

## Unresolved (fail loudly; consolidated in `EXECUTION_PLAN.md`)
- **P5-1** Speech accuracy on real dialogue is not measured. Speech is validated on synthetic speech (macOS text-to-speech, `tests/fixtures/speech_16k.wav`: 0.95 of windows read as speech), on silence and on tones. On the local clip the classifier finds 0.1% speech in the first chunk, and the clip's real speech content is not known.
- **P5-2** The music label is a heuristic (tonal, not speech) and is validated only on tones and noise. On the local clip 97% of the first chunk is labelled music. That is unverified.
- **P5-3** Loudness is validated on one 80 s stereo clip (whole-film integrated -33.94 LUFS against ffmpeg `ebur128` -34.0 LUFS). Not validated over full films, for surround (5.1 is downmixed by ffmpeg, not BS.1770-weighted), or for true peak (`peak_dbfs` is sample peak).
- **P5-4** Audio/video alignment on real files is unmeasured. Audio is read from film time 0, with no correction for a container offset between the streams.
- **P5-5** The nightly real-clip job now asserts audio, but it has not run on GitHub since this change (the local run passed). It runs on `main` after merge.

## Review against the Phase 5 section (evidence)

| Aspect (EXECUTION_PLAN Phase 5) | Evidence |
|---|---|
| Tests first, unit then integration | Written before the implementation: `test_audio_chunk.py`, `test_loudness.py`, `test_audio_argv.py`, `test_audio_decode.py`, `test_model_integrity.py`, `test_speech_music.py`, `test_av_pipeline.py`. Written after: `test_vad.py`, `test_model_fetch.py`, `test_model_loading.py` (their subjects were built first, so the order is not strictly test-first for these three; they were then exercised against the code they guard). Unit: 86 tests (`test_audio_chunk` 15, `test_loudness` 20, `test_audio_argv` 21, `test_model_integrity` 17, `test_speech_music` 13). Integration: 23 (`test_audio_decode` 9, `test_vad` 9, `test_av_pipeline` 5), plus architecture 7 and the real-clip pair |
| Synthetic audio with known silence, tone and noise | `tests/fixtures/make_synthetic.py::make_av_clip` (silence 0 to 2 s, 440 Hz tone 2 to 4 s, silence after) and the noise in `test_speech_music.py` |
| Loudness asserted against reference values | `test_loudness.py`: the published 48 kHz K-weighting coefficients (1e-9), the 16 kHz response within 0.15 dB of 48 kHz to 4 kHz, steady sines against the BS.1770 arithmetic, gating (absolute and relative), silence floor, core-only measurement. Real footage: -33.94 vs -34.0 LUFS (ebur128) |
| Timestamp alignment with video chunks | `test_audio_decode.py`: the window starts on the film clock (first tone sample at 2.00006 s against 2.0 s; within 2 samples), chunk audio lines up with chunk frames including the overlap, and `test_av_pipeline.py::test_each_chunk_reports_the_audio_it_contains` |
| Deliver: `extractors/loudness.py`, `extractors/speech_music.py`, Silero via ONNX Runtime | Both files exist; the classifier is pure and the loudness is pure; the model runs in `media/vad.py` (`test_vad.py`: silence, tone, noise, TTS speech, shape, determinism) |
| Security: model file hash verified | `test_model_integrity.py` (tampered, missing, oversize, unpinned, malformed manifest) and `test_the_shipped_model_matches_its_pinned_manifest` (SHA-256 `1a153a22...88e3`, the shipped file) |
| Security: no network download at runtime | `tests/architecture/test_model_loading.py` (onnxruntime and `InferenceSession` only in `media/vad.py`), `test_security_patterns.py` (no network imports, passing in `make check`), `test_model_fetch.py` (HTTPS-only argv, verify before write). `make models` was the only network call in this session |
| Security: model file ships in the wheel | `test_wheel_resources.py` (wheel contains the model, manifest and licence) |
| Exit: green build | `make check` exit 0 (log below) |
| Exit: combined video and audio pipeline test on the synthetic clip | `tests/integration/test_av_pipeline.py` (5 tests: per-chunk values, video and audio stored together, silent film, byte-identical reruns, kill and resume equal to an uninterrupted run) |
| Exit: extractors plug in through the protocol and registry | `test_registry.py` (a new extractor is discovered without touching existing modules, still passing); the audio extractors were added as modules with no edit to existing extractors |
| Architecture rules | 300-line cap (`test_file_size.py`): largest new file `media/audio.py` 141 lines, `core/chunk.py` 145; functions and complexity (`test_function_limits.py`); frozen dataclasses (`test_frozen_dataclasses.py`); no hardcoded strings or colours; layers (`test_layer_imports.py`, `media` imports only `core`, `extractors` only `core`); no `shell=True`, no pickle (bandit, `test_security_patterns.py`) |
| Pure core, thin shell | `extractors/` and `core/` import no I/O (layer test). The only I/O is in `media/`, `pipeline/` and `storage/` |

## Evidence: measurements

- **Real footage** (`IMG_0309.MOV`, 80 s, 1080p HEVC, stereo AAC 48 kHz, local): `filmanalyser` exit 0, 15.5 s wall, 341 MB peak RSS. Stage times on this clip: video decode 13.9 s (pre-existing HEVC decode), audio decode 0.09 s, voice detection 0.19 s, extraction 0.2 to 0.6 s per chunk. Audio costs are small next to video decode.
- **Loudness cross-check**: whole-film integrated -33.94 LUFS (ours, 16 kHz, stereo) against -34.0 LUFS (`ffmpeg ebur128`, 48 kHz). Sample peak -0.87 dBFS against true peak -0.3 dBFS (consistent: sample peak does not exceed true peak).
- **VAD on TTS speech** (5.9 s): 0.946 of windows at or above 0.5. A 440 Hz tone at most 0.0024; white noise at most 0.043; digital silence at most 0.009.
- **Music heuristic** (flatness, 512-sample Hann windows): pure tone and four-tone chord at most 0.0000; white noise 0.495 to 0.609. Threshold 0.2.
- **Nightly benchmark** (`make nightly`, local): 10-minute synthetic film with audio, 7.4 s wall, 81.3 film-s per wall-s, peak RSS 320 MB. 4 slow tests passed.
- **Real-clip target** (`FILMANALYSER_REAL_CLIP=/Users/sunil/Downloads/IMG_0309.MOV make real-clip`): 2 passed (kill and resume equals an uninterrupted run with audio; audio features well formed).

## Decisions added (`DECISIONS.md` #59 to #66)
59 licence allowlist name for protobuf · 60 per-chunk audio decode · 61 loudness at 16 kHz, sample peak · 62 Silero model vendored in the package, verified, fetched only by `make models` · 63 speech, music and silence labels and thresholds · 64 needs_audio and video-only films · 65 voice state per window · 66 reference arithmetic and ring-out.

## CI (PR #7)

- First run (head `6fef07d`): macOS green; Ubuntu failed on the synthetic audio fixture (MP4 rejects PCM on ffmpeg 6.0.1), recorded as debt item 17.
- Fix in `c17e3b8`. Run 43241830014 on head `3e4339e`: `make check (macos-latest)` and `make check (ubuntu-latest)` both green.

## Build confirmation: raw `make check` output (ANSI stripped)

```text
uv run --locked ruff check .
All checks passed!
uv run --locked ruff format --check .
126 files already formatted
uv run --locked mypy
Success: no issues found in 114 source files
uv run --locked pytest tests/unit tests/architecture tests/integration -m "not real_clip and not slow"
============================= test session starts ==============================
platform darwin -- Python 3.12.14, pytest-9.2.0, pluggy-1.7.0
rootdir: /Users/sunil/Downloads/FilmAnalyser
configfile: pyproject.toml
plugins: platformdirs-4.14.5, hypothesis-6.170.15, cov-7.1.0
collected 608 items / 6 deselected / 602 selected

tests/unit/test_audio_argv.py .....................                      [  3%]
tests/unit/test_audio_chunk.py ...............                           [  5%]
tests/unit/test_chunk.py ............................                    [ 10%]
tests/unit/test_chunker.py ..............                                [ 12%]
tests/unit/test_color.py .........                                       [ 14%]
tests/unit/test_config.py ................                               [ 17%]
tests/unit/test_errors.py .........                                      [ 18%]
tests/unit/test_events.py ...........                                    [ 20%]
tests/unit/test_feature_store.py ...........................             [ 24%]
tests/unit/test_ffmpeg_stream.py ..........                              [ 26%]
tests/unit/test_files.py .........................                       [ 30%]
tests/unit/test_letterbox.py .....                                       [ 31%]
tests/unit/test_loudness.py ....................                         [ 34%]
tests/unit/test_manifest.py .............................                [ 39%]
tests/unit/test_model_integrity.py .................                     [ 42%]
tests/unit/test_paths.py ................                                [ 45%]
tests/unit/test_probe.py .................                               [ 48%]
tests/unit/test_registry.py .....................                        [ 51%]
tests/unit/test_renderer.py .......                                      [ 52%]
tests/unit/test_resources.py ..........................                  [ 56%]
tests/unit/test_runner.py .........                                      [ 58%]
tests/unit/test_schema.py ..............................                 [ 63%]
tests/unit/test_shot_cuts.py ..........                                  [ 65%]
tests/unit/test_speech_music.py .............                            [ 67%]
tests/unit/test_viewmodel.py ......                                      [ 68%]
tests/architecture/test_atomic_writes.py ....                            [ 68%]
tests/architecture/test_ci_workflow.py ..........                        [ 70%]
tests/architecture/test_color_contrast.py ..........................     [ 74%]
tests/architecture/test_error_keys.py ....                               [ 75%]
tests/architecture/test_file_size.py ......                              [ 76%]
tests/architecture/test_frozen_dataclasses.py ....                       [ 77%]
tests/architecture/test_function_limits.py ...                           [ 77%]
tests/architecture/test_layer_imports.py ............                    [ 79%]
tests/architecture/test_model_fetch.py .....                             [ 80%]
tests/architecture/test_model_loading.py ..                              [ 80%]
tests/architecture/test_nightly_workflow.py ........                     [ 82%]
tests/architecture/test_no_hardcoded_colors.py ........                  [ 83%]
tests/architecture/test_no_hardcoded_strings.py ..........               [ 85%]
tests/architecture/test_no_skips.py ...                                  [ 85%]
tests/architecture/test_security_patterns.py ..............              [ 88%]
tests/architecture/test_subprocess_argv.py .....                         [ 88%]
tests/integration/test_audio_decode.py .........                         [ 90%]
tests/integration/test_av_pipeline.py .....                              [ 91%]
tests/integration/test_cli.py .....                                      [ 92%]
tests/integration/test_decode_stream.py ................                 [ 94%]
tests/integration/test_determinism.py ...                                [ 95%]
tests/integration/test_extract_budget.py .                               [ 95%]
tests/integration/test_ffmpeg_version.py .                               [ 95%]
tests/integration/test_memory_flat.py ...                                [ 96%]
tests/integration/test_resume.py ......                                  [ 97%]
tests/integration/test_resume_grid.py ..                                 [ 97%]
tests/integration/test_vad.py .........                                  [ 98%]
tests/integration/test_video_pipeline.py ......                          [ 99%]
tests/integration/test_wheel_resources.py .                              [100%]

================================ tests coverage ================================
______________ coverage: platform darwin, python 3.12.14-final-0 _______________

Name    Stmts   Miss Branch BrPart  Cover   Missing
---------------------------------------------------
TOTAL    1504      0    284      0   100%

42 files skipped due to complete coverage.
Required test coverage of 90% reached. Total coverage: 100.00%
====================== 602 passed, 6 deselected in 29.78s ======================
mkdir -p .cache
uv export --locked --no-emit-project --format requirements-txt -o .cache/audit-requirements.txt >/dev/null
Resolved 73 packages in 2ms
uv run --locked pip-audit --require-hashes --disable-pip -r .cache/audit-requirements.txt
No known vulnerabilities found
uv run --locked pip-licenses --allow-only="MIT License;MIT;BSD License;3-Clause BSD License;BSD-2-Clause;BSD-3-Clause;Apache Software License;Apache-2.0;Apache-2.0 OR BSD-2-Clause;Python Software Foundation License;PSF-2.0;ISC License (ISCL);MPL-2.0;Mozilla Public License 2.0 (MPL 2.0);The Unlicense (Unlicense);BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0" --format=plain >/dev/null
gitleaks dir . --no-banner --redact -v
8:22PM INF scanned ~6251847 bytes (6.25 MB) in 415ms
8:22PM INF no leaks found
uv run --locked bandit -q -r src scripts -c pyproject.toml
uv build --wheel --out-dir dist
Building wheel...
Successfully built dist/filmanalyser-0.1.0-py3-none-any.whl
uv run --locked python scripts/guard_selftest.py
  ok   file over 300 lines: caught
  ok   core imports report: caught
  ok   pure core imports os: caught
  ok   view imports analysis: caught
  ok   literal string in cli: caught
  ok   hex colour in report: caught
  ok   mutable dataclass: caught
  ok   function over 40 lines: caught
  ok   direct file write in storage (not atomic): caught
  ok   inline ffmpeg argv (option injection): caught
  ok   unknown error message key: caught
  ok   shell=True in media: caught
  ok   pickle import: caught
  ok   eval call: caught
  ok   network import: caught
  ok   subprocess outside media: caught
  ok   security suppression comment: caught
  ok   bandit: shell=True: caught
  ok   complexity over 10: caught
  ok   more than 5 arguments: caught
  ok   untyped function (mypy --strict): caught
  ok   coverage below gate: caught
  ok   ffprobe path no longer after `--`: caught
  ok   ffmpeg input loses file: protocol lock: caught
  ok   path validation accepts directories: caught
  ok   path validation accepts NUL bytes: caught
  ok   resume no longer seeks (re-decodes finished chunks): caught
  ok   atomic write loses its rename: caught
  ok   store accepts a symlink in place of a file: caught
  ok   store accepts a path with directories (traversal): caught
  ok   file reads are no longer size-bounded: caught
  ok   feature version mismatch is accepted (mixed outputs): caught
  ok   chunk hash is no longer verified: caught
  ok   store accepts out-of-order or repeated chunks (not append-only): caught
  ok   test that skips (no skips rule): caught
  ok   extractor imports media (layer rule): caught
  ok   plain English text in the CLI (not from strings.toml): caught
  ok   resume grid re-anchored to the first decoded frame (P3-1): caught
  ok   boundary cut dropped (overlap not compared): caught
  ok   report not autoescaped: caught
  ok   report allows external requests (CSP removed): caught
  ok   letterbox bars from one dark frame (median removed): caught
  ok   nightly workflow gets write access: caught
  ok   template literal text: caught
  ok   template |safe output: caught
  ok   committed secret (gitleaks): caught
  ok   vulnerable pin (pip-audit): caught
  ok   disallowed licence: caught
guard self-test: 0 failing guard(s)
```

## Real-clip confirmation: `FILMANALYSER_REAL_CLIP=/Users/sunil/Downloads/IMG_0309.MOV make real-clip`

```text
uv run --locked pytest -m real_clip --no-cov
============================= test session starts ==============================
platform darwin -- Python 3.12.14, pytest-9.2.0, pluggy-1.7.0
rootdir: /Users/sunil/Downloads/FilmAnalyser
configfile: pyproject.toml
testpaths: tests
plugins: platformdirs-4.14.5, hypothesis-6.170.15, cov-7.1.0
collected 608 items / 606 deselected / 2 selected

tests/integration/test_real_clip_smoke.py ..                             [100%]

====================== 2 passed, 606 deselected in 46.34s ======================
```

## Follow-up: open items (branch `feat/phase-5-open-items`)

Requested: address all open items. Status per item:

| Item | Status | What was done | Evidence |
|---|---|---|---|
| P5-4 Audio/video alignment | **Closed** | The audio window follows the container clock. The picture's start and the track's start are probed; a track that starts late gets a silent lead (DECISIONS #67). The first version of this fix was wrong (it shifted the seek); the tests caught it and the design was corrected | `tests/integration/test_audio_offset.py` (5 tests, incl. the control that shows the old behaviour puts the tone 0.5 s early) |
| P5-3 Loudness | **Narrowed, still open** | Surround (5.1) weighting and true peak are implemented (DECISIONS #68). True peak reads 0.36 dB low on the local clip because audio is decoded at 16 kHz | `test_loudness.py` (surround: +1.49 dB for a surround channel, LFE excluded; true peak: 4 kHz at 45 degrees within 0.2 dB of 0 dBFS). Real clip: true peak -0.66 dBFS against ebur128 -0.3 dBFS |
| P5-5 Nightly real-clip job | **Ran; found a defect in my assertion; fixed; re-run pending merge** | The first post-merge nightly (run 43245241801) failed `peak_dbfs <= 0`. Decoded float PCM can exceed full scale, so the assertion was wrong; the bound is now +6 dBFS (DECISIONS #69) | Local real-clip run after the fix: 2 passed. The nightly is re-run after merge |
| P5-1 Speech on real dialogue | **Blocked on input** | Nothing new to measure: no labelled real dialogue is in the repo, and I cannot label speech by ear | Needs labels from you (see below) |
| P5-2 Music label | **Blocked on input** | Same: no labelled real music. The heuristic is unchanged | Needs labels from you (see below) |
| P4-4 Real-footage cut accuracy (Phase 8 item) | **Blocked on input** | No hand-labelled cuts exist for the local clip | Needs labels from you |
| P4-3 Fades and dissolves (Phase 8 item) | **Not started** | It is a new detector with its own synthetic ground truth. It belongs to Phase 8 by the plan, and I have not started it in this follow-up | Pending in EXECUTION_PLAN |

### What I need from you to close the blocked items
1. Three familiar films (or excerpts, a few minutes each) with hand labels: speech spans, music spans and cut times. A simple text file of start and end seconds per label is enough. Without labels, P5-1, P5-2 and P4-4 cannot be measured honestly.
2. For P5-3, the `ebur128` readings of the same three films (`ffmpeg -i film -af ebur128=peak=true -f null -`), so I can compare full-film loudness.
3. Once the 48 kHz true-peak decode is built, the same films show whether the 0.36 dB bias is gone.

### Decisions added in this follow-up
67 audio/picture alignment on the container clock · 68 surround weights and true peak · 69 over-full-scale decoded values
