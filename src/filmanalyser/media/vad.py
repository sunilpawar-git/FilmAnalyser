"""Voice activity detection with Silero VAD on ONNX Runtime (DECISIONS #62, #65).

The model ships inside the package (`filmanalyser/models/`). Before any byte is handed to ONNX
Runtime, its SHA-256 is checked against `MANIFEST.sha256`. Nothing is downloaded at run time: the
explicit setup command `scripts/fetch_models.py` is the only place the model comes from.

The model reads 512-sample windows (32 ms at 16 kHz) and carries a recurrent state; each window is
preceded by the last 64 samples of the one before, as the v5+ model expects. Its output is a speech
probability per window, computed from the start of the window it is given (no state from before).
"""

import dataclasses
import hashlib
import hmac
import os
import re
from collections.abc import Iterable, Iterator
from importlib import resources
from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt
import onnxruntime as ort  # type: ignore[import-untyped]

from filmanalyser.core.chunk import Chunk, Samples
from filmanalyser.core.config import AUDIO_RATE, MODEL_MAX_BYTES, VOICE_CONTEXT, VOICE_WINDOW
from filmanalyser.core.errors import ModelError

MODEL_NAME = "silero_vad.onnx"
MANIFEST_NAME = "MANIFEST.sha256"
_HASH = re.compile(r"^[0-9a-f]{64}$")
_STATE_SHAPE = (2, 1, 128)  # the model's recurrent state (the v5+ Silero layout)


def model_dir() -> Path:
    """The directory the model and its manifest ship in (inside the installed package)."""
    return Path(str(resources.files("filmanalyser") / "models"))


def parse_manifest(text: str) -> dict[str, str]:
    """`sha256  file-name` lines (the `sha256sum` format) as a mapping; anything else is refused."""
    pins: dict[str, str] = {}
    for line in text.splitlines():
        if not line.strip():
            continue
        parts = line.split("  ", 1)
        if len(parts) != 2 or not _HASH.match(parts[0]) or parts[1] != Path(parts[1]).name:
            raise ModelError(key="error.model.default", name=MANIFEST_NAME)
        if parts[1] in pins:
            raise ModelError(key="error.model.default", name=MANIFEST_NAME)
        pins[parts[1]] = parts[0]
    return pins


def verify_bytes(data: bytes, expected: str) -> None:
    """Refuse `data` unless its SHA-256 is `expected` (constant-time comparison)."""
    actual = hashlib.sha256(data).hexdigest()
    if not hmac.compare_digest(actual, expected):
        raise ModelError(key="error.model.default", name=MODEL_NAME)


def _read_bounded(path: Path) -> bytes:
    """The file's bytes, refusing anything larger than MODEL_MAX_BYTES before it is read."""
    try:
        if os.stat(path).st_size > MODEL_MAX_BYTES:
            raise ModelError(key="error.model.default", name=path.name)
        return path.read_bytes()
    except OSError:
        raise ModelError(key="error.model.default", name=path.name) from None


def read_verified(directory: Path) -> bytes:
    """The model's bytes, if and only if they match the manifest in `directory`."""
    pins = parse_manifest(_read_bounded(directory / MANIFEST_NAME).decode("utf-8", "replace"))
    if MODEL_NAME not in pins:
        raise ModelError(key="error.model.default", name=MODEL_NAME)
    data = _read_bounded(directory / MODEL_NAME)
    verify_bytes(data, pins[MODEL_NAME])
    return data


class VoiceDetector:
    """A loaded, verified Silero session. One per process: loading is the expensive part."""

    def __init__(self, model: bytes) -> None:
        try:
            self._session: Any = ort.InferenceSession(model, providers=["CPUExecutionProvider"])
        except Exception:  # onnxruntime raises several types for a malformed model
            raise ModelError(key="error.model.default", name=MODEL_NAME) from None

    @classmethod
    def load(cls, directory: Path | None = None) -> "VoiceDetector":
        return cls(read_verified(model_dir() if directory is None else directory))

    def probabilities(self, mono: Samples) -> npt.NDArray[np.float32]:
        """Speech probability of each whole window of `mono` (a 1-D float32 signal at AUDIO_RATE).
        A trailing part shorter than one window gets no probability."""
        signal = np.asarray(mono, dtype=np.float32).reshape(-1)
        count = len(signal) // VOICE_WINDOW
        out = np.zeros(count, dtype=np.float32)
        state = np.zeros(_STATE_SHAPE, dtype=np.float32)
        rate = np.array(AUDIO_RATE, dtype=np.int64)
        context = np.zeros(VOICE_CONTEXT, dtype=np.float32)
        for index in range(count):
            block = signal[index * VOICE_WINDOW : (index + 1) * VOICE_WINDOW]
            feed = np.concatenate([context, block])[None, :]
            prob, state = self._session.run(
                ["output", "stateN"], {"input": feed, "state": state, "sr": rate}
            )
            out[index] = float(prob[0, 0])
            context = block[-VOICE_CONTEXT:]
        return out


def attach_voice(chunks: Iterable[Chunk], detector: VoiceDetector) -> Iterator[Chunk]:
    """Each chunk whose audio carries the speech probability of its window (mono mix)."""
    for chunk in chunks:
        audio = chunk.audio
        if audio is None:
            yield chunk
            continue
        mono = np.mean(audio.samples, axis=1, dtype=np.float32)
        voice = detector.probabilities(mono)
        yield dataclasses.replace(chunk, audio=dataclasses.replace(audio, voice=voice))
