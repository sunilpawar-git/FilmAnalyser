"""The built wheel ships the resource files and the typing marker (a source-tree test would
not notice a packaging mistake)."""

import subprocess
import zipfile
from pathlib import Path

from tests.architecture._scan import REPO

EXPECTED = {
    "filmanalyser/py.typed",
    "filmanalyser/report/resources/strings.toml",
    "filmanalyser/report/resources/colors.toml",
    "filmanalyser/models/silero_vad.onnx",  # the pinned VAD model (DECISIONS #62)
    "filmanalyser/models/MANIFEST.sha256",
    "filmanalyser/models/LICENSE-silero-vad.txt",
}


def test_built_wheel_contains_resources(tmp_path: Path) -> None:
    subprocess.run(
        ["uv", "build", "--wheel", "--out-dir", str(tmp_path)],
        cwd=REPO,
        check=True,
        capture_output=True,
        timeout=120,
    )
    (wheel,) = tmp_path.glob("filmanalyser-*.whl")
    with zipfile.ZipFile(wheel) as archive:
        assert set(archive.namelist()) >= EXPECTED
