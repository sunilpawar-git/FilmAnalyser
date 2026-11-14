"""The release workflow (plan, Phase 8): a `v*` tag runs the full suite, then builds the wheel and
the SBOM, then publishes. Same supply-chain rules as CI: pinned actions, least privilege, and a
single job that can write. Dependency updates come through Dependabot and the same gate."""

import re

from tests.architecture._scan import REPO

RELEASE = (REPO / ".github/workflows/release.yml").read_text(encoding="utf-8")
CI = (REPO / ".github/workflows/ci.yml").read_text(encoding="utf-8")
DEPENDABOT = (REPO / ".github/dependabot.yml").read_text(encoding="utf-8")
MAKEFILE = (REPO / "Makefile").read_text(encoding="utf-8")


def _job(name: str) -> str:
    return RELEASE.split(f"\n  {name}:\n", 1)[1].split("\n\n", 1)[0]


def test_a_v_tag_starts_the_release() -> None:
    assert re.search(r'on:\s*\n\s+push:\s*\n\s+tags:\s*\["v\*"\]', RELEASE)
    assert "pull_request" not in RELEASE


def test_the_full_suite_is_ci_itself_and_runs_first() -> None:
    assert "uses: ./.github/workflows/ci.yml" in _job("check")
    assert "workflow_call:" in CI
    assert "needs: check" in _job("build")
    assert "needs: build" in _job("publish")


def test_the_build_makes_the_wheel_the_sbom_and_the_notes() -> None:
    build = _job("build")
    assert "make release-assets" in build
    assert "scripts/release_notes.py" in build
    assert re.search(r'bin/filmanalyser" --version', build)  # the wheel is run, not only built


def test_release_assets_are_a_wheel_an_sbom_and_checksums() -> None:
    recipe = MAKEFILE.split("\nrelease-assets:", 1)[1].split("\n\n", 1)[0]
    assert "build" in recipe.splitlines()[0] and "sbom" in recipe.splitlines()[0]
    assert "SHA256SUMS" in recipe
    assert "cyclonedx-py" in MAKEFILE


def test_only_the_publish_job_can_write() -> None:
    assert re.search(r"^permissions:\s*\n\s+contents: read\s*$", RELEASE, re.MULTILINE)
    writers = re.findall(r"contents: write", RELEASE)
    assert len(writers) == 1 and "contents: write" in _job("publish")


def test_actions_are_pinned_to_commit_shas() -> None:
    refs = re.findall(r"uses:\s*(\S+)", RELEASE)
    assert refs
    assert all(re.search(r"@[0-9a-f]{40}$", r) or r.startswith("./") for r in refs), refs


def test_the_checksums_are_verified_before_publishing_and_the_tag_must_exist() -> None:
    publish = _job("publish")
    assert "shasum -a 256 -c SHA256SUMS" in publish
    assert "--verify-tag" in publish


def test_dependabot_covers_the_lock_file_and_the_action_pins() -> None:
    ecosystems = re.findall(r"package-ecosystem:\s*(\S+)", DEPENDABOT)
    assert sorted(ecosystems) == ["github-actions", "uv"]
    assert DEPENDABOT.count("commit-message:") == 2  # Conventional Commits for the changelog
