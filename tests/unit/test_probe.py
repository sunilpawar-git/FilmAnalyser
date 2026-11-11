"""ffprobe wrapper: argv shape, output parsing, and failure modes (fake tools, no real media)."""

import json
import stat
import sys
from pathlib import Path

import pytest

from filmanalyser.core.errors import DecodeError
from filmanalyser.media.probe import VideoInfo, parse_probe, probe_argv, probe_video

GOOD = {
    "streams": [{"width": 1920, "height": 1080, "duration": "7200.5", "start_time": "0.0417"}],
    "format": {"duration": "7200.6", "start_time": "0.0"},
}


def _fake_ffprobe(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, body: str) -> None:
    tool = tmp_path / "ffprobe"
    tool.write_text(f"#!{sys.executable}\nimport sys\n{body}\n")
    tool.chmod(tool.stat().st_mode | stat.S_IXUSR)
    monkeypatch.setenv("PATH", str(tmp_path))


def test_argv_passes_the_path_last_after_double_dash() -> None:
    argv = probe_argv("/usr/bin/ffprobe", Path("/films/-evil.mp4"))
    assert argv[0] == "/usr/bin/ffprobe"
    assert argv[-2:] == ["--", "/films/-evil.mp4"]
    assert "shell" not in " ".join(argv)


def test_parse_reads_stream_values() -> None:
    info = parse_probe(json.dumps(GOOD))
    assert info == VideoInfo(width=1920, height=1080, duration_s=7200.5, start_s=0.0417)


def test_parse_falls_back_to_format_duration() -> None:
    data = {
        "streams": [{"width": 640, "height": 360, "duration": "N/A"}],
        "format": {"duration": "9.5"},
    }
    assert parse_probe(json.dumps(data)).duration_s == 9.5


def test_parse_skips_non_finite_durations() -> None:
    data = {"streams": [{"width": 8, "height": 8, "duration": "nan"}], "format": {"duration": "5"}}
    assert parse_probe(json.dumps(data)).duration_s == 5.0


@pytest.mark.parametrize(
    "text",
    [
        "not json",
        "[]",
        json.dumps({"streams": [], "format": {"duration": "1"}}),
        json.dumps({"streams": [{"width": 0, "height": 10, "duration": "1"}]}),
        json.dumps({"streams": [{"width": 10, "height": 10, "duration": "N/A"}], "format": {}}),
        json.dumps({"streams": [{"width": 10, "height": 10, "duration": "-3"}]}),
        json.dumps({"streams": [{"width": "wide", "height": 10, "duration": "3"}]}),
    ],
)
def test_parse_rejects_unusable_output(text: str) -> None:
    with pytest.raises(DecodeError):
        parse_probe(text)


def test_no_video_stream_has_its_own_error_key() -> None:
    with pytest.raises(DecodeError) as info:
        parse_probe(json.dumps({"streams": [], "format": {"duration": "1"}}))
    assert info.value.key == "error.decode.no_video"


def test_scaled_size_keeps_aspect_and_even_height() -> None:
    assert VideoInfo(1920, 1080, 1.0, 0.0).scaled_size(160) == (160, 90)
    assert VideoInfo(1920, 800, 1.0, 0.0).scaled_size(160) == (160, 66)
    assert VideoInfo(100, 1000, 1.0, 0.0).scaled_size(160) == (160, 1600)
    assert VideoInfo(4000, 10, 1.0, 0.0).scaled_size(160)[1] == 2  # never below 2


def test_probe_video_runs_the_tool_and_parses(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    film = tmp_path / "f.mp4"
    film.write_bytes(b"x")
    _fake_ffprobe(tmp_path, monkeypatch, f"sys.stdout.write({json.dumps(GOOD)!r})")
    assert probe_video(film).width == 1920


def test_probe_failure_reports_exit_code_and_scrubs_the_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    film = tmp_path / "f.mp4"
    film.write_bytes(b"x")
    _fake_ffprobe(tmp_path, monkeypatch, f"sys.stderr.write({str(film)!r} + ': bad'); sys.exit(1)")
    with pytest.raises(DecodeError) as info:
        probe_video(film)
    assert info.value.key == "error.decode.probe_failed"
    assert str(tmp_path) not in str(info.value)


def test_probe_output_is_bounded(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    film = tmp_path / "f.mp4"
    film.write_bytes(b"x")
    _fake_ffprobe(tmp_path, monkeypatch, "sys.stdout.write('x' * 5_000_000)")
    with pytest.raises(DecodeError) as info:
        probe_video(film)
    assert info.value.key == "error.decode.probe_failed"


def test_probe_times_out(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    film = tmp_path / "f.mp4"
    film.write_bytes(b"x")
    _fake_ffprobe(tmp_path, monkeypatch, "import time; time.sleep(30)")
    with pytest.raises(DecodeError) as info:
        probe_video(film, timeout_s=0.5)
    assert info.value.key == "error.decode.probe_failed"
