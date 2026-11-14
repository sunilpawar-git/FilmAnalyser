"""Opt-in voice separation with Demucs (DECISIONS #88). Demucs is an external tool, like ffmpeg: it
is installed by the user (it brings PyTorch, which the project does not depend on) and called with
an argument list built in one place. Its model weights are fetched once by an explicit setup command
(`make separation-model`), pinned in `models/SEPARATION.sha256` and verified before every run; the
model folder is passed with `--repo`, so Demucs never downloads anything.

A batch of chunk windows is written as 16-bit WAV files to a working folder, separated in one run
(the model loads once per run), and each voice stem is read back at AUDIO_RATE, mono.
"""

import hashlib
import hmac
import os
import shutil
import subprocess
import wave
from collections.abc import Mapping
from dataclasses import dataclass
from importlib import resources
from pathlib import Path

import numpy as np
import numpy.typing as npt

from filmanalyser.core.chunk import Samples
from filmanalyser.core.config import (
    AUDIO_RATE,
    SEPARATION_MAX_MODEL_BYTES,
    SEPARATION_TIMEOUT_S,
    SILENCE_DBFS,
    SPEECH_PROB,
    STDERR_LIMIT_BYTES,
    VOICE_WINDOW,
)
from filmanalyser.core.errors import DecodeError, InputError, ModelError
from filmanalyser.media.audio import PcmFormat, decode_window
from filmanalyser.media.paths import scrub_stderr
from filmanalyser.media.vad import parse_manifest

TOOL = "demucs"
MODEL = "htdemucs"
STEM = "vocals"
MANIFEST_NAME = "SEPARATION.sha256"
MODEL_DIR_ENV = "FILMANALYSER_SEPARATION_MODEL"
_HASH_BLOCK = 1024 * 1024


@dataclass(frozen=True)
class Separator:
    """A Demucs executable and a verified model folder."""

    tool: str
    model_dir: Path


def default_model_dir() -> Path:
    """Where `make separation-model` puts the model and the CLI looks for it: the folder named by
    FILMANALYSER_SEPARATION_MODEL, else ~/.cache/filmanalyser/htdemucs."""
    named = os.environ.get(MODEL_DIR_ENV, "")
    return Path(named) if named else Path.home() / ".cache" / "filmanalyser" / MODEL


def separation_pins() -> dict[str, str]:
    """The pinned SHA-256 of each model file, from the manifest shipped in the package."""
    text = (resources.files("filmanalyser") / "models" / MANIFEST_NAME).read_text(encoding="utf-8")
    return parse_manifest(text)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(_HASH_BLOCK), b""):
            digest.update(block)
    return digest.hexdigest()


def verify_model_dir(model_dir: Path, pins: Mapping[str, str]) -> None:
    """Refuse the folder unless each pinned file is there, bounded in size, with its pinned hash."""
    for name, expected in pins.items():
        path = model_dir / name
        try:
            if not path.is_file() or path.stat().st_size > SEPARATION_MAX_MODEL_BYTES:
                raise ModelError(key="error.model.separation", name=name)
            actual = _sha256(path)
        except OSError:
            raise ModelError(key="error.model.separation", name=name) from None
        if not hmac.compare_digest(actual, expected):
            raise ModelError(key="error.model.separation", name=name)


def find_separator(model_dir: Path, pins: Mapping[str, str] | None = None) -> Separator:
    """The Demucs tool on PATH and the verified model folder, or an error that says what to do."""
    tool = shutil.which(TOOL)
    if tool is None:
        raise InputError(key="error.input.no_separator", tool=TOOL)
    verify_model_dir(model_dir, separation_pins() if pins is None else pins)
    return Separator(tool, model_dir)


def separate_argv(tool: str, model_dir: Path, out_dir: Path, inputs: list[Path]) -> list[str]:
    """One Demucs run: voice and the rest, the pinned model from `model_dir`. `--shifts 0` turns off
    Demucs's random time shift, so the same input always gives the same stem (with its default the
    stem changed by up to 0.2 between two runs). The device is Demucs's own choice: the GPU when
    there is one, else the CPU; with no shift they agree to one 16-bit step. The input files come
    after `--`, so none of them can be read as an option."""
    return [
        tool, f"--two-stems={STEM}", "-n", MODEL, "--repo", str(model_dir), "--shifts", "0",
        "-o", str(out_dir), "--filename", "{track}.{stem}.{ext}", "--", *map(str, inputs),
    ]  # fmt: skip


def background_dbfs(mono: npt.NDArray[np.float32], voice: npt.NDArray[np.float32]) -> float:
    """The level of a window's background: the median level of its windows that are sound but not
    speech. It tracks the real music-and-effects level (correlation 0.99 on Tears of Steel)."""
    count = min(len(voice), len(mono) // VOICE_WINDOW)
    blocks = mono[: count * VOICE_WINDOW].astype(np.float64).reshape(count, VOICE_WINDOW)
    level = 20 * np.log10(np.maximum(np.sqrt(np.mean(blocks * blocks, axis=1)), 1e-12))
    bed = level[(voice[:count] < SPEECH_PROB) & (level >= SILENCE_DBFS)]
    return float(np.median(bed)) if bed.size else -120.0


def write_wav(path: Path, samples: Samples, rate: int) -> None:
    """16-bit PCM WAV of a (count, channels) float window (clipped to full scale)."""
    pcm = (np.clip(samples, -1.0, 1.0) * 32767).astype("<i2")
    with wave.open(str(path), "wb") as out:
        out.setnchannels(samples.shape[1])
        out.setsampwidth(2)
        out.setframerate(rate)
        out.writeframes(pcm.tobytes())


def separate_windows(
    separator: Separator, windows: Mapping[int, tuple[Samples, int]], work_dir: Path
) -> dict[int, npt.NDArray[np.float32]]:
    """Voice stems, mono at AUDIO_RATE, for a batch of windows keyed by chunk index. Each window is
    (samples, rate). One Demucs run separates the whole batch."""
    inputs = []
    for index, (samples, rate) in windows.items():
        path = work_dir / f"chunk_{index:06d}.wav"
        write_wav(path, samples, rate)
        inputs.append(path)
    argv = separate_argv(separator.tool, separator.model_dir, work_dir / "out", inputs)
    try:
        done = subprocess.run(
            argv, check=False, capture_output=True, timeout=SEPARATION_TIMEOUT_S,
            stdin=subprocess.DEVNULL,
        )  # fmt: skip
    except subprocess.TimeoutExpired:
        raise DecodeError(key="error.decode.separation_failed", code=-1) from None
    if done.returncode != 0:
        detail = scrub_stderr(done.stderr, work_dir, STDERR_LIMIT_BYTES)
        raise DecodeError(detail, key="error.decode.separation_failed", code=done.returncode)
    stems = {}
    for index, (samples, rate) in windows.items():
        stem = work_dir / "out" / MODEL / f"chunk_{index:06d}.{STEM}.wav"
        duration = len(samples) / rate
        stems[index] = decode_window(stem, 0.0, duration, PcmFormat(1, AUDIO_RATE))[:, 0]
    return stems
