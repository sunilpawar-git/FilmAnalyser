"""Records the ffmpeg in use (visible with `pytest -s` and in CI logs) and enforces a floor."""

import re
import subprocess

MIN_MAJOR = 6  # CI pins 6.0.1 (Linux) and 9.0.2 (macOS); development runs 9.x


def test_ffmpeg_and_ffprobe_meet_the_minimum_version() -> None:
    for tool in ("ffmpeg", "ffprobe"):
        out = subprocess.run([tool, "-version"], check=True, capture_output=True, text=True).stdout
        first = out.splitlines()[0]
        print(f"\n{first}")
        found = re.search(r"version\D*(\d+)\.", first)
        assert found, first
        assert int(found.group(1)) >= MIN_MAJOR, first
