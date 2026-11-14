"""Structured logging: one JSON object per event, scalars only, paths reduced to basenames."""

import json
import logging
from pathlib import Path

import numpy as np
import pytest

from filmanalyser.core.events import format_event, log_event
from filmanalyser.media import telemetry
from filmanalyser.media.telemetry import parse_vm_hwm, peak_rss_mb


def test_event_is_one_json_object() -> None:
    line = format_event("chunk", {"index": 3, "seconds": 1.5})
    assert json.loads(line) == {"event": "chunk", "index": 3, "seconds": 1.5}
    assert "\n" not in line


def test_paths_are_logged_by_basename_only() -> None:
    line = format_event("decode_start", {"film": "/Users/someone/Movies/private/film.mp4"})
    assert json.loads(line)["film"] == "film.mp4"
    assert "someone" not in line


def test_windows_style_paths_are_reduced_too() -> None:
    assert json.loads(format_event("e", {"film": "C:\\Users\\x\\film.mp4"}))["film"] == "film.mp4"


@pytest.mark.parametrize("value", [b"raw bytes", np.zeros(3), [1, 2], {"a": 1}, None])
def test_film_content_and_containers_are_refused(value: object) -> None:
    with pytest.raises(TypeError, match="scalar"):
        format_event("chunk", {"data": value})  # type: ignore[dict-item]


def test_event_name_cannot_be_overridden_by_a_field() -> None:
    with pytest.raises(ValueError, match="event"):
        format_event("chunk", {"event": "spoofed"})


def test_log_event_writes_through_the_standard_logger(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO, logger="filmanalyser"):
        log_event("chunk", index=0, rss_mb=12.5)
    assert [json.loads(r.getMessage()) for r in caplog.records] == [
        {"event": "chunk", "index": 0, "rss_mb": 12.5}
    ]


def test_peak_rss_is_a_plausible_megabyte_figure() -> None:
    value = peak_rss_mb()
    assert 5 < value < 100_000


def test_the_linux_peak_is_read_from_vm_hwm() -> None:
    status = "Name:\tpython\nVmPeak:\t 900000 kB\nVmHWM:\t   51200 kB\nVmRSS:\t   40960 kB\n"
    assert parse_vm_hwm(status) == 50.0
    assert parse_vm_hwm("Name:\tpython\n") is None


def test_the_own_peak_is_used_where_the_system_reports_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    status = tmp_path / "status"
    status.write_text("VmHWM:\t 2048 kB\n", encoding="ascii")
    monkeypatch.setattr(telemetry, "_STATUS", status)
    assert peak_rss_mb() == 2.0


@pytest.mark.parametrize("content", [None, "Name:\tpython\n"])
def test_without_vm_hwm_the_process_peak_is_used(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, content: str | None
) -> None:
    status = tmp_path / "status"  # missing (macOS) or without the line
    if content is not None:
        status.write_text(content, encoding="ascii")
    monkeypatch.setattr(telemetry, "_STATUS", status)
    assert 5 < peak_rss_mb() < 100_000
