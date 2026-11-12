"""Explicit setup step (DECISIONS #62): fetch the pinned Silero VAD model once, check it against the
manifest shipped in the package, and write it there. Run by hand with `make models`.

Nothing else in the project touches the network, and the application never does at run time. The
download is refused unless its SHA-256 matches the manifest, and the file is written only after that
check, so a bad download never replaces a good model.
"""

import os
import subprocess
import sys
import tempfile
from pathlib import Path

from filmanalyser.core.config import MODEL_MAX_BYTES
from filmanalyser.core.errors import ModelError
from filmanalyser.media.vad import (
    MANIFEST_NAME,
    MODEL_NAME,
    model_dir,
    parse_manifest,
    verify_bytes,
)

# The release the manifest pins. Changing the model means changing this URL and the manifest hash
# together, in one reviewed commit.
MODEL_URL = "https://github.com/snakers4/silero-vad/raw/v6.2.3/src/silero_vad/data/silero_vad.onnx"
DOWNLOAD_TIMEOUT_S = 120


def download_argv(curl: str, url: str, target: Path) -> list[str]:
    """curl over HTTPS only, following the release redirect, bounded in size and time."""
    return [
        curl, "--fail", "--silent", "--show-error", "--location",
        "--proto", "=https", "--proto-redir", "=https", "--tlsv1.2",
        "--max-time", str(DOWNLOAD_TIMEOUT_S), "--max-filesize", str(MODEL_MAX_BYTES),
        "--output", str(target), "--", MODEL_URL,
    ]  # fmt: skip


def fetch(target: Path) -> None:
    subprocess.run(
        download_argv("curl", MODEL_URL, target), check=True, timeout=DOWNLOAD_TIMEOUT_S + 30
    )


def install(data: bytes, directory: Path) -> Path:
    """Check `data` against the manifest in `directory`, then write it there atomically."""
    pins = parse_manifest((directory / MANIFEST_NAME).read_text(encoding="utf-8"))
    if MODEL_NAME not in pins:
        raise ModelError(key="error.model.default", name=MODEL_NAME)
    verify_bytes(data, pins[MODEL_NAME])
    final = directory / MODEL_NAME
    staging = final.with_suffix(".onnx.partial")
    staging.write_bytes(data)
    os.replace(staging, final)
    return final


def main() -> int:
    directory = model_dir()
    with tempfile.TemporaryDirectory() as scratch:
        downloaded = Path(scratch) / MODEL_NAME
        try:
            fetch(downloaded)
            install(downloaded.read_bytes(), directory)
        except (ModelError, subprocess.SubprocessError, OSError) as error:
            print(f"model not installed: {error}", file=sys.stderr)
            return 1
    print(f"installed {MODEL_NAME} into {directory}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
