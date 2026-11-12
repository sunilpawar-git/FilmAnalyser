"""The audio command lines and probe parsing (pure: no process is started here)."""

import json
import subprocess
from pathlib import Path

import numpy as np
import pytest

from filmanalyser.core.config import AUDIO_RATE
from filmanalyser.core.errors import DecodeError, InputError
from filmanalyser.media.audio import (
    _fit,
    audio_channels,
    audio_probe_argv,
    decode_argv,
    decode_window,
    parse_audio_channels,
)

FILM = Path("film.mp4")  # a relative name: these functions only build argument lists


def _argv(start: float = 1.5, duration: float = 2.0, channels: int = 2) -> list[str]:
    return decode_argv("/usr/bin/ffmpeg", FILM, start, duration, channels)


def test_decode_argv_is_a_list_with_the_tool_first() -> None:
    argv = _argv()
    assert isinstance(argv, list)
    assert all(isinstance(part, str) for part in argv)
    assert argv[0] == "/usr/bin/ffmpeg"


def test_the_input_is_a_file_protocol_path_and_only_files_are_allowed() -> None:
    argv = _argv()
    assert argv[argv.index("-protocol_whitelist") + 1] == "file"
    assert argv.index("-protocol_whitelist") < argv.index("-i")
    assert argv[argv.index("-i") + 1] == f"file:{FILM}"


def test_seek_and_duration_are_fixed_point_numbers() -> None:
    argv = _argv(start=1.5, duration=2.0)
    assert argv[argv.index("-ss") + 1] == "1.500000"
    assert argv[argv.index("-t") + 1] == "2.000000"
    assert argv.index("-ss") < argv.index("-i") < argv.index("-t")  # seek before, duration after


def test_output_is_mono_or_stereo_float32_at_the_audio_rate() -> None:
    argv = _argv(channels=2)
    assert argv[argv.index("-ac") + 1] == "2"
    assert argv[argv.index("-ar") + 1] == str(AUDIO_RATE)
    assert argv[argv.index("-f") + 1] == "f32le"
    assert argv[argv.index("-acodec") + 1] == "pcm_f32le"
    assert argv[-1] == "pipe:1"


def test_only_the_first_audio_stream_is_decoded_and_no_video_is_kept() -> None:
    argv = _argv()
    assert argv[argv.index("-map") + 1] == "0:a:0"
    assert {"-vn", "-sn", "-dn"} <= set(argv)


def test_a_zero_or_negative_window_is_refused() -> None:
    with pytest.raises(InputError):
        _argv(duration=0.0)
    with pytest.raises(InputError):
        _argv(start=-1.0)


def test_probe_argv_ends_options_before_the_path() -> None:
    argv = audio_probe_argv("/usr/bin/ffprobe", FILM)
    assert argv[argv.index("--") + 1] == str(FILM)
    assert argv[argv.index("-select_streams") + 1] == "a:0"


def test_no_audio_stream_gives_none() -> None:
    assert parse_audio_channels(json.dumps({"streams": []})) is None


def test_mono_and_stereo_are_reported_as_they_are() -> None:
    assert parse_audio_channels(json.dumps({"streams": [{"channels": 1}]})) == 1
    assert parse_audio_channels(json.dumps({"streams": [{"channels": 2}]})) == 2


def test_more_than_two_channels_are_downmixed_to_stereo() -> None:
    assert parse_audio_channels(json.dumps({"streams": [{"channels": 6}]})) == 2


@pytest.mark.parametrize(
    "text",
    [
        "not json",
        json.dumps({"streams": [{"channels": 0}]}),
        json.dumps({"streams": [{"channels": "two"}]}),
        json.dumps({"streams": [{"channels": True}]}),
        json.dumps({"streams": [{}]}),
    ],
)
def test_unusable_probe_output_is_a_decode_error(text: str) -> None:
    with pytest.raises(DecodeError):
        parse_audio_channels(text, name="film.mp4")


def test_a_probe_whose_streams_are_not_a_list_is_a_decode_error() -> None:
    with pytest.raises(DecodeError):
        parse_audio_channels(json.dumps({"streams": 5}))


def test_a_probe_stream_that_is_not_an_object_is_a_decode_error() -> None:
    with pytest.raises(DecodeError):
        parse_audio_channels(json.dumps({"streams": ["mono"]}))


def test_a_timed_out_probe_is_a_decode_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def expired(*_args: object, **_kwargs: object) -> None:
        raise subprocess.TimeoutExpired(cmd="ffprobe", timeout=1)

    monkeypatch.setattr(subprocess, "run", expired)
    with pytest.raises(DecodeError) as info:
        audio_channels(FILM)
    assert info.value.key == "error.decode.probe_failed"


def test_a_timed_out_decode_is_an_audio_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    def expired(*_args: object, **_kwargs: object) -> None:
        raise subprocess.TimeoutExpired(cmd="ffmpeg", timeout=1)

    monkeypatch.setattr(subprocess, "run", expired)
    with pytest.raises(DecodeError) as info:
        decode_window(FILM, 0.0, 1.0, 1)
    assert info.value.key == "error.decode.audio_failed"


def test_a_short_track_is_padded_with_silence_and_a_long_one_is_cut() -> None:
    short = np.array([0.5, -0.5], dtype=np.float32).tobytes()  # two mono samples
    padded = _fit(short, count=4, channels=1)
    assert padded[:, 0].tolist() == [0.5, -0.5, 0.0, 0.0]
    long = np.arange(6, dtype=np.float32).tobytes()
    assert _fit(long, count=4, channels=1)[:, 0].tolist() == [0.0, 1.0, 2.0, 3.0]


def test_a_torn_final_sample_is_dropped_not_misread() -> None:
    raw = np.array([0.25, 0.75], dtype=np.float32).tobytes() + b"\x01\x02"  # 2 bytes of a sample
    assert _fit(raw, count=3, channels=1)[:, 0].tolist() == [0.25, 0.75, 0.0]
