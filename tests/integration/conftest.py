"""ffmpeg is a hard requirement of the integration tests: a missing tool fails the build loudly
(DECISIONS #38). It is never a reason to skip."""

import pytest

from tests.fixtures.make_synthetic import ffmpeg_available


@pytest.fixture(autouse=True, scope="session")
def require_ffmpeg() -> None:
    if not ffmpeg_available():
        pytest.fail(
            "ffmpeg and ffprobe are required on PATH (see README: Requirements)", pytrace=False
        )
