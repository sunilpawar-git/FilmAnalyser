"""End to end on real ffmpeg: a synthetic clip decodes into the expected chunks and durations."""

import json
import logging
from pathlib import Path

import numpy as np
import pytest

from filmanalyser.core.chunk import Chunk, expected_chunks
from filmanalyser.core.config import Config
from filmanalyser.core.errors import DecodeError, InputError
from filmanalyser.media.ffmpeg_stream import decode_chunks
from filmanalyser.media.probe import probe_video
from tests.fixtures.make_synthetic import (
    FPS,
    RAMP_PERIOD_S,
    SIZE,
    concat_clip,
    make_clip,
)

CONFIG = Config(chunk_seconds=10.0, overlap_seconds=1.0, analysis_fps=10.0, frame_width=64)


@pytest.fixture(scope="module")
def two_minutes(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return make_clip(tmp_path_factory.mktemp("clips") / "two_min.mp4", seconds=120)


def _luma(frame: np.ndarray) -> float:
    return float(frame.mean())


def test_probe_reports_the_synthetic_clip(two_minutes: Path) -> None:
    info = probe_video(two_minutes)
    assert (info.width, info.height) == SIZE
    assert info.duration_s == pytest.approx(120.0, abs=0.5)
    assert info.start_s == pytest.approx(0.0, abs=0.1)


def test_two_minute_clip_gives_the_expected_chunk_count_and_durations(two_minutes: Path) -> None:
    chunks = list(decode_chunks(two_minutes, CONFIG))
    assert len(chunks) == expected_chunks(120 * FPS, CONFIG.frames_per_chunk) == 12
    assert [c.index for c in chunks] == list(range(12))
    assert all(c.duration_s == pytest.approx(10.0) for c in chunks)
    assert chunks[-1].end_s == pytest.approx(120.0)


def test_frames_are_downscaled_to_the_analysis_size(two_minutes: Path) -> None:
    first = next(iter(decode_chunks(two_minutes, CONFIG)))
    assert first.frames.shape[1:] == (36, 64, 3)  # 320x180 -> 64 wide, aspect kept
    assert first.frames.dtype == np.uint8


def test_first_chunk_has_no_context_and_later_ones_have_one_second(two_minutes: Path) -> None:
    chunks = list(decode_chunks(two_minutes, CONFIG))
    assert chunks[0].context_frames == 0
    assert {c.context_frames for c in chunks[1:]} == {10}


def test_overlap_frames_are_identical_to_the_previous_tail(two_minutes: Path) -> None:
    chunks = list(decode_chunks(two_minutes, CONFIG))
    for prev, cur in zip(chunks[:3], chunks[1:4], strict=True):
        assert np.array_equal(cur.frames[: cur.context_frames], prev.core[-cur.context_frames :])


def test_frame_timing_follows_the_ground_truth_ramp(two_minutes: Path) -> None:
    """Luma is a sawtooth of film time, so each frame's brightness reveals its timestamp."""
    first = next(iter(decode_chunks(two_minutes, CONFIG)))
    luma = np.array([_luma(f) for f in first.core])
    expected = 255 * (np.arange(len(luma)) / FPS % RAMP_PERIOD_S) / RAMP_PERIOD_S
    ok = np.abs(luma - expected) < 25  # tolerance covers codec quantisation and the wrap frame
    assert ok.mean() > 0.95


def test_timestamps_are_normalised_to_start_at_zero(tmp_path: Path) -> None:
    shifted = make_clip(tmp_path / "shifted.mp4", seconds=20, offset=600.0)
    assert probe_video(shifted).start_s == pytest.approx(600.0, abs=0.2)  # the container says 600 s
    chunks = list(decode_chunks(shifted, CONFIG))
    assert chunks[0].start_s == 0.0  # ...but the first frame is film time zero
    assert len(chunks) == 2
    assert chunks[-1].end_s == pytest.approx(20.0, abs=0.2)


def test_short_final_chunk(tmp_path: Path) -> None:
    clip = make_clip(tmp_path / "odd.mp4", seconds=25)
    chunks = list(decode_chunks(clip, CONFIG))
    assert [round(c.duration_s, 1) for c in chunks] == [10.0, 10.0, 5.0]


def test_chunks_satisfy_the_extractor_input_contract(two_minutes: Path) -> None:
    chunk = next(iter(decode_chunks(two_minutes, CONFIG)))
    assert isinstance(chunk, Chunk)
    assert not chunk.frames.flags.writeable


def test_garbage_file_is_a_decode_error(tmp_path: Path) -> None:
    junk = tmp_path / "junk.mp4"
    junk.write_bytes(b"this is not a film" * 100)
    with pytest.raises(DecodeError):
        list(decode_chunks(junk, CONFIG))


def test_missing_file_is_an_input_error(tmp_path: Path) -> None:
    with pytest.raises(InputError):
        list(decode_chunks(tmp_path / "absent.mp4", CONFIG))


def test_dash_leading_file_name_decodes_normally(tmp_path: Path) -> None:
    """Option injection: a file called `-f.mp4` is data, never an ffmpeg option."""
    clip = make_clip(tmp_path / "-f.mp4", seconds=12)
    assert len(list(decode_chunks(clip, CONFIG))) == 2


def test_concat_helper_builds_a_longer_film(tmp_path: Path) -> None:
    base = make_clip(tmp_path / "b.mp4", seconds=10)
    longer = concat_clip(base, tmp_path / "long.mp4", times=3)
    assert probe_video(longer).duration_s == pytest.approx(30.0, abs=1.0)


def test_decoding_logs_structured_events_without_paths(
    two_minutes: Path, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.INFO, logger="filmanalyser"):
        chunks = list(decode_chunks(two_minutes, CONFIG))
    events = [json.loads(r.getMessage()) for r in caplog.records]
    per_chunk = [e for e in events if e["event"] == "chunk"]
    assert len(per_chunk) == len(chunks) == 12
    assert all(e["decode_s"] >= 0 and e["peak_rss_mb"] > 0 for e in per_chunk)
    assert {e["film"] for e in events if "film" in e} == {"two_min.mp4"}  # basename only
    assert events[-1] == {"event": "decode_done", "film": "two_min.mp4", "chunks": 12}
    assert str(two_minutes.parent) not in caplog.text


def test_resuming_at_a_chunk_reproduces_that_chunk_without_decoding_the_earlier_ones(
    two_minutes: Path, caplog: pytest.LogCaptureFixture
) -> None:
    full = list(decode_chunks(two_minutes, CONFIG))
    with caplog.at_level(logging.INFO, logger="filmanalyser"):
        resumed = list(decode_chunks(two_minutes, CONFIG, start_chunk=7))
    assert [c.index for c in resumed] == [7, 8, 9, 10, 11]
    for got, want in zip(resumed, full[7:], strict=True):
        assert (got.start_s, got.end_s, got.context_frames) == (
            want.start_s,
            want.end_s,
            want.context_frames,
        )
        assert np.array_equal(got.frames, want.frames)  # bit-identical, so features are too
    decoded = sum(json.loads(r.getMessage()).get("frames", 0) for r in caplog.records)
    assert decoded == sum(len(c.frames) for c in full[7:])  # nothing before chunk 7's context


def test_resuming_past_the_end_of_the_film_is_a_decode_error(two_minutes: Path) -> None:
    with pytest.raises(DecodeError):
        list(decode_chunks(two_minutes, CONFIG, start_chunk=40))
