"""ffmpeg streaming: argv safety, bounded stderr, failure mapping, process cleanup.
A fake `ffmpeg` (a tiny Python script on PATH) stands in so these tests need no real media."""

import stat
import sys
import time
from pathlib import Path

import pytest

from filmanalyser.core.config import STDERR_LIMIT_BYTES, Config
from filmanalyser.core.errors import DecodeError
from filmanalyser.media.ffmpeg_stream import Seek, decode_argv, stream_frames

CONFIG = Config(chunk_seconds=1.0, overlap_seconds=0.0, analysis_fps=10.0, frame_width=4)
SIZE = (4, 2)  # width, height -> 24 bytes per rgb24 frame


def _fake_ffmpeg(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, body: str) -> Path:
    tool = tmp_path / "ffmpeg"
    tool.write_text(f"#!{sys.executable}\nimport sys, time\n{body}\n")
    tool.chmod(tool.stat().st_mode | stat.S_IXUSR)
    monkeypatch.setenv("PATH", str(tmp_path))
    film = tmp_path / "film.mp4"
    film.write_bytes(b"x")
    return film


def test_argv_is_a_list_with_a_file_protocol_input_and_no_audio() -> None:
    argv = decode_argv("/usr/bin/ffmpeg", Path("/films/-evil.mp4"), CONFIG, SIZE)
    assert isinstance(argv, list)
    i = argv.index("-i")
    assert argv[i + 1] == "file:/films/-evil.mp4"  # forced file protocol, absolute path
    assert argv.index("-protocol_whitelist") < i  # applies to the input
    assert argv[argv.index("-protocol_whitelist") + 1] == "file"
    assert "-an" in argv
    assert argv[-1] == "pipe:1"
    assert "-nostdin" in argv


def test_argv_seeks_before_the_input_only_when_resuming() -> None:
    plain = decode_argv("ffmpeg", Path("/f.mp4"), CONFIG, SIZE)
    assert "-ss" not in plain
    argv = decode_argv("ffmpeg", Path("/f.mp4"), CONFIG, SIZE, Seek(start_s=118.0))
    assert argv[argv.index("-ss") + 1] == "118.0"
    assert argv.index("-ss") < argv.index("-i")  # input seeking: skipped film is never decoded


def test_argv_applies_pts_normalisation_fps_and_scale() -> None:
    argv = decode_argv("ffmpeg", Path("/f.mp4"), CONFIG, SIZE, Seek(origin_s=0.5))
    vf = argv[argv.index("-vf") + 1]
    assert vf.startswith(
        "setpts=PTS-0.5/TB,"
    )  # the stream's own start is removed, not the seek point
    assert "fps=10.0" in vf
    assert "scale=4:2" in vf


def test_argv_keeps_source_timestamps_so_a_seek_does_not_rebase_them() -> None:
    """DECISIONS #54: timestamps stay on the container clock; the grid ignores the seek point."""
    argv = decode_argv("ffmpeg", Path("/f.mp4"), CONFIG, SIZE, Seek(5.0, 0.0))
    assert argv.index("-copyts") < argv.index("-i")
    assert argv.index("-copyts") < argv.index("-ss") < argv.index("-i")


def test_frames_are_yielded_with_the_requested_shape(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    film = _fake_ffmpeg(tmp_path, monkeypatch, "sys.stdout.buffer.write(bytes(range(24)) * 3)")
    frames = list(stream_frames(film, CONFIG, SIZE))
    assert len(frames) == 3
    assert frames[0].shape == (2, 4, 3)
    assert frames[0].flatten().tolist() == list(range(24))


def test_nonzero_exit_is_a_decode_error_with_scrubbed_bounded_stderr(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    film = tmp_path / "film.mp4"
    body = f"sys.stderr.write({str(film)!r} + ' broken ' + 'e' * 100000); sys.exit(7)"
    film = _fake_ffmpeg(tmp_path, monkeypatch, body)
    with pytest.raises(DecodeError) as info:
        list(stream_frames(film, CONFIG, SIZE))
    err = info.value
    assert err.key == "error.decode.ffmpeg_failed"
    assert err.fields["code"] == 7
    assert len(str(err)) < STDERR_LIMIT_BYTES + 200
    assert str(tmp_path) not in str(err)


def test_chatty_stderr_cannot_deadlock_the_pipe(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    body = "sys.stderr.write('w' * 3_000_000); sys.stdout.buffer.write(bytes(24) * 2)"
    film = _fake_ffmpeg(tmp_path, monkeypatch, body)
    assert len(list(stream_frames(film, CONFIG, SIZE))) == 2


def test_early_close_kills_the_process(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    marker = tmp_path / "pid"
    body = (
        f"open({str(marker)!r}, 'w').write(str(__import__('os').getpid()))\n"
        "sys.stdout.buffer.write(bytes(24)); sys.stdout.flush(); time.sleep(60)"
    )
    film = _fake_ffmpeg(tmp_path, monkeypatch, body)
    gen = stream_frames(film, CONFIG, SIZE)
    next(gen)
    gen.close()
    pid = int(marker.read_text())
    time.sleep(0.2)
    with pytest.raises(ProcessLookupError):
        __import__("os").kill(pid, 0)


def test_missing_ffmpeg_fails_before_spawning(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PATH", str(tmp_path))
    with pytest.raises(DecodeError) as info:
        list(stream_frames(tmp_path / "film.mp4", CONFIG, SIZE))
    assert info.value.key == "error.decode.tool_missing"


def test_zero_frames_is_a_decode_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    film = _fake_ffmpeg(tmp_path, monkeypatch, "pass")
    with pytest.raises(DecodeError) as info:
        list(stream_frames(film, CONFIG, SIZE))
    assert info.value.key == "error.decode.no_frames"
