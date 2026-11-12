"""The nightly workflow runs the slow checks, and the real-clip job only when a clip is configured
by repository variables (DECISIONS #53). It follows the same supply-chain rules as CI."""

import re

from tests.architecture._scan import REPO

NIGHTLY = (REPO / ".github/workflows/nightly.yml").read_text(encoding="utf-8")
ACTION = (REPO / ".github/actions/setup-ffmpeg/action.yml").read_text(encoding="utf-8")
MAKEFILE = (REPO / "Makefile").read_text(encoding="utf-8")


def test_nightly_runs_the_slow_and_real_clip_targets() -> None:
    assert "make nightly" in NIGHTLY
    assert "make real-clip" in NIGHTLY


def test_real_clip_job_runs_only_when_a_clip_is_configured() -> None:
    assert re.search(r"if:\s*\$\{\{\s*vars\.REAL_CLIP_URL\s*!=\s*''\s*\}\}", NIGHTLY)


def test_the_real_clip_is_checksum_verified_before_use() -> None:
    assert "vars.REAL_CLIP_SHA256" in NIGHTLY
    assert "sha256sum -c" in NIGHTLY or "shasum -a 256 -c" in NIGHTLY


def test_nightly_uses_least_privilege_and_pinned_actions() -> None:
    assert re.search(r"^permissions:\s*\n\s+contents: read\s*$", NIGHTLY, re.MULTILINE)
    refs = re.findall(r"uses:\s*(\S+)", NIGHTLY)
    assert refs
    assert all(re.search(r"@[0-9a-f]{40}$", ref) or ref.startswith("./") for ref in refs), refs


def test_ffmpeg_comes_from_the_shared_composite_action() -> None:
    assert "./.github/actions/setup-ffmpeg" in NIGHTLY


def test_the_ffmpeg_pins_live_once_in_the_composite_action() -> None:
    for name in ("FFMPEG_VERSION", "FFMPEG_MAC_VERSION"):
        assert re.search(rf"{name}:\s*\"\d+\.\d+(\.\d+)?\"", ACTION), name
    assert "brew install ffmpeg" not in ACTION


def test_make_nightly_and_real_clip_targets_exist() -> None:
    assert re.search(r"^nightly:", MAKEFILE, re.MULTILINE)
    assert re.search(r"^real-clip:", MAKEFILE, re.MULTILINE)
