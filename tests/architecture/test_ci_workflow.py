"""CI runs the same definition of green as local: `make ci` -> `make check`, on macOS + Linux."""

import re

from tests.architecture._scan import REPO

WORKFLOW = (REPO / ".github/workflows/ci.yml").read_text(encoding="utf-8")
MAKEFILE = (REPO / "Makefile").read_text(encoding="utf-8")


def test_ci_runs_make_ci() -> None:
    assert re.search(r"^\s*(?:-\s*)?run:\s*make ci\s*$", WORKFLOW, re.MULTILINE)


def test_make_ci_runs_make_check() -> None:
    recipe = MAKEFILE.split("\nci:", 1)[1].split("\n\n", 1)[0]
    assert "$(MAKE) check" in recipe


def test_matrix_covers_macos_and_linux() -> None:
    assert "macos-latest" in WORKFLOW
    assert "ubuntu-latest" in WORKFLOW


def test_workflow_uses_least_privilege() -> None:
    assert re.search(r"^permissions:\s*\n\s+contents: read\s*$", WORKFLOW, re.MULTILINE)


def test_actions_are_pinned_to_commit_shas() -> None:
    refs = re.findall(r"uses:\s*(\S+)", WORKFLOW)
    assert refs
    assert all(re.search(r"@[0-9a-f]{40}$", ref) for ref in refs), refs


def test_make_check_stage_order_is_fail_fast() -> None:
    line = next(ln for ln in MAKEFILE.splitlines() if ln.startswith("check:"))
    stages = line.split("##")[0].replace("check:", "").split()
    assert stages == ["lint", "typecheck", "test", "security", "build", "guards"]


def test_ffmpeg_is_pinned_by_version_and_checksum_on_both_oses() -> None:
    for name in ("FFMPEG_VERSION", "FFMPEG_MAC_VERSION"):
        assert re.search(rf"{name}:\s*\"\d+\.\d+(\.\d+)?\"", WORKFLOW), name
    for name in ("FFMPEG_LINUX_SHA256", "FFMPEG_MAC_SHA256", "FFPROBE_MAC_SHA256"):
        assert re.search(rf"{name}:\s*\"[0-9a-f]{{64}}\"", WORKFLOW), name
    assert "brew install ffmpeg" not in WORKFLOW  # Homebrew cannot pin a version


def test_ffmpeg_downloads_are_checksum_verified_and_cached() -> None:
    linux = WORKFLOW.split("Install ffmpeg (Linux")[1].split("- name:")[0]
    mac = WORKFLOW.split("Install ffmpeg (macOS")[1].split("- name:")[0]
    assert "sha256sum -c" in linux
    assert mac.count("shasum -a 256 -c") == 2  # ffmpeg and ffprobe
    assert WORKFLOW.count("actions/cache@") == 2  # one per OS


def test_ci_logs_the_ffmpeg_version() -> None:
    assert "ffmpeg -version" in WORKFLOW
