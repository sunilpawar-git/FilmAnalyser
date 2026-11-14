"""Explicit setup step (DECISIONS #62, #88): fetch a pinned model once, check it against the
manifest shipped in the package, and install it. `make models` fetches the Silero VAD model into
the package; `make separation-model` (`--separation [DIR]`) fetches the opt-in voice-separation
model (Demucs htdemucs, MIT) into its own folder, outside the package (84 MB).

Nothing else in the project touches the network, and the application never does at run time. The
download is refused unless its SHA-256 matches the manifest, and the file is written only after that
check, so a bad download never replaces a good model.
"""

import argparse
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from filmanalyser.core.config import MODEL_MAX_BYTES, SEPARATION_MAX_MODEL_BYTES
from filmanalyser.core.errors import ModelError
from filmanalyser.media.separation import default_model_dir, separation_pins, verify_model_dir
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
SEPARATION_URL = "https://dl.fbaipublicfiles.com/demucs/hybrid_transformer/955717e8-8726e21a.th"
SEPARATION_WEIGHTS = "955717e8-8726e21a.th"
SEPARATION_RECIPE = ("htdemucs.yaml", b"models: ['955717e8']\n")  # pinned in SEPARATION.sha256
DOWNLOAD_TIMEOUT_S = 900


def download_argv(curl: str, url: str, target: Path, max_bytes: int) -> list[str]:
    """curl over HTTPS only, following the release redirect, bounded in size and time."""
    return [
        curl, "--fail", "--silent", "--show-error", "--location",
        "--proto", "=https", "--proto-redir", "=https", "--tlsv1.2",
        "--max-time", str(DOWNLOAD_TIMEOUT_S), "--max-filesize", str(max_bytes),
        "--output", str(target), "--", url,
    ]  # fmt: skip


def fetch(url: str, target: Path, max_bytes: int) -> None:
    argv = download_argv("curl", url, target, max_bytes)
    subprocess.run(argv, check=True, timeout=DOWNLOAD_TIMEOUT_S + 30)


def install_separation(staging: Path, directory: Path, pins: dict[str, str]) -> Path:
    """Write the recipe beside the downloaded weights in `staging`, verify both against `pins`,
    and only then move them into `directory`. A bad download never replaces a good model."""
    name, recipe = SEPARATION_RECIPE
    (staging / name).write_bytes(recipe)
    verify_model_dir(staging, pins)
    directory.mkdir(parents=True, exist_ok=True)
    for file_name in pins:
        os.replace(staging / file_name, directory / file_name)
    return directory


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


def _install_vad(scratch: Path) -> Path:
    downloaded = scratch / MODEL_NAME
    fetch(MODEL_URL, downloaded, MODEL_MAX_BYTES)
    return install(downloaded.read_bytes(), model_dir())


def _install_separation(scratch: Path, directory: Path) -> Path:
    fetch(SEPARATION_URL, scratch / SEPARATION_WEIGHTS, SEPARATION_MAX_MODEL_BYTES)
    return install_separation(scratch, directory, separation_pins())


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Fetch a pinned model once (verified).")
    parser.add_argument("--separation", nargs="?", const=str(default_model_dir()), default=None)
    args = parser.parse_args(argv)
    with tempfile.TemporaryDirectory() as scratch:
        try:
            if args.separation is None:
                where = _install_vad(Path(scratch))
            else:
                where = _install_separation(Path(scratch), Path(args.separation))
        except (ModelError, subprocess.SubprocessError, OSError) as error:
            print(f"model not installed: {error}", file=sys.stderr)
            return 1
    print(f"installed into {where}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
