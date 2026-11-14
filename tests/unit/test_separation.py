"""Opt-in voice separation (DECISIONS #88): the Demucs command, the model check, the rule that picks
which chunks to separate, and the merge of the stem's voice into the chunk's."""

import hashlib
import os
import stat
import wave
from pathlib import Path

import numpy as np
import pytest

from filmanalyser.core.config import (
    GEOMETRY_FIELDS,
    SEPARATION_BED_DBFS,
    VOICE_WINDOW,
    Config,
)
from filmanalyser.core.errors import InputError, ModelError
from filmanalyser.media import separation
from filmanalyser.media.separation import (
    MODEL,
    MODEL_DIR_ENV,
    STEM,
    background_dbfs,
    default_model_dir,
    find_separator,
    separate_argv,
    separation_pins,
    verify_model_dir,
    write_wav,
)
from filmanalyser.pipeline.runner import separator_for
from filmanalyser.pipeline.voices import _fit


def _pinned(tmp_path: Path, files: dict[str, bytes]) -> tuple[Path, dict[str, str]]:
    folder = tmp_path / "model"
    folder.mkdir()
    for name, data in files.items():
        (folder / name).write_bytes(data)
    return folder, {name: hashlib.sha256(data).hexdigest() for name, data in files.items()}


# ---- the command ---------------------------------------------------------------------------------


def test_the_separation_command_uses_the_pinned_model_offline() -> None:
    argv = separate_argv("/bin/demucs", Path("/m"), Path("/out"), [Path("a.wav"), Path("-b.wav")])
    assert argv[0] == "/bin/demucs"
    assert f"--two-stems={STEM}" in argv
    assert argv[argv.index("-n") + 1] == MODEL
    assert argv[argv.index("--repo") + 1] == "/m"  # the local folder: no download
    assert argv[argv.index("--shifts") + 1] == "0"  # no random shift: the same stem every run
    assert argv[argv.index("-o") + 1] == "/out"
    assert argv[argv.index("--") + 1 :] == ["a.wav", "-b.wav"]  # inputs are never options


# ---- the model -----------------------------------------------------------------------------------


def test_the_shipped_manifest_pins_the_weights_and_the_recipe() -> None:
    assert set(separation_pins()) == {"955717e8-8726e21a.th", "htdemucs.yaml"}


def test_a_folder_that_matches_its_pins_is_accepted(tmp_path: Path) -> None:
    folder, pins = _pinned(tmp_path, {"w.th": b"weights", "r.yaml": b"recipe"})
    verify_model_dir(folder, pins)


@pytest.mark.parametrize("damage", ["missing", "tampered", "a_folder"])
def test_a_folder_that_does_not_match_is_refused(tmp_path: Path, damage: str) -> None:
    folder, pins = _pinned(tmp_path, {"w.th": b"weights"})
    (folder / "w.th").unlink()
    if damage == "tampered":
        (folder / "w.th").write_bytes(b"other weights")
    if damage == "a_folder":
        (folder / "w.th").mkdir()
    with pytest.raises(ModelError) as caught:
        verify_model_dir(folder, pins)
    assert caught.value.key == "error.model.separation"


def test_an_oversized_file_is_refused_before_it_is_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    folder, pins = _pinned(tmp_path, {"w.th": b"weights"})
    monkeypatch.setattr(separation, "SEPARATION_MAX_MODEL_BYTES", 3)
    with pytest.raises(ModelError):
        verify_model_dir(folder, pins)


def test_an_unreadable_file_is_refused(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    folder, pins = _pinned(tmp_path, {"w.th": b"weights"})

    def refuse(path: Path) -> str:
        raise PermissionError(path)

    monkeypatch.setattr(separation, "_sha256", refuse)
    with pytest.raises(ModelError):
        verify_model_dir(folder, pins)


def _fake_tool(folder: Path) -> Path:
    tool = folder / "demucs"
    tool.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    tool.chmod(tool.stat().st_mode | stat.S_IXUSR)
    return tool


def test_the_separator_needs_the_tool_on_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    folder, pins = _pinned(tmp_path, {"w.th": b"weights"})
    monkeypatch.setenv("PATH", str(tmp_path / "empty"))
    with pytest.raises(InputError) as caught:
        find_separator(folder, pins)
    assert caught.value.key == "error.input.no_separator"


def test_the_separator_is_the_tool_and_the_verified_folder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    folder, pins = _pinned(tmp_path, {"w.th": b"weights"})
    tool = _fake_tool(tmp_path)
    monkeypatch.setenv("PATH", str(tmp_path) + os.pathsep + os.environ["PATH"])
    found = find_separator(folder, pins)
    assert Path(found.tool) == tool and found.model_dir == folder


def test_the_separator_refuses_a_model_that_fails_its_check(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    folder, pins = _pinned(tmp_path, {"w.th": b"weights"})
    (folder / "w.th").write_bytes(b"tampered")
    _fake_tool(tmp_path)
    monkeypatch.setenv("PATH", str(tmp_path) + os.pathsep + os.environ["PATH"])
    with pytest.raises(ModelError):
        find_separator(folder, pins)


def test_the_model_folder_defaults_to_the_user_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(MODEL_DIR_ENV, raising=False)
    assert default_model_dir() == Path.home() / ".cache" / "filmanalyser" / MODEL
    monkeypatch.setenv(MODEL_DIR_ENV, "/somewhere/else")
    assert default_model_dir() == Path("/somewhere/else")


# ---- the setting ---------------------------------------------------------------------------------


def test_separation_is_off_unless_asked_for() -> None:
    assert separator_for(Config()) is None


def test_separation_without_a_model_folder_is_refused() -> None:
    with pytest.raises(InputError) as caught:
        Config(separate_voices=True)
    assert caught.value.fields["name"] == "separation_model"


def test_separation_is_part_of_what_stored_features_were_computed_under() -> None:
    assert "separate_voices" in GEOMETRY_FIELDS
    assert Config().geometry()["separate_voices"] == 0.0
    on = Config(separate_voices=True, separation_model="/m").geometry()
    assert on["separate_voices"] == 1.0
    assert all(type(value) is float for value in on.values())  # the manifest refuses bools
    assert "separation_model" not in on  # where the model lives does not change the features


# ---- which chunks are separated ------------------------------------------------------------------


def _level(dbfs: float, windows: int) -> np.ndarray:
    """A steady signal at `dbfs` (a square wave: its RMS is its amplitude)."""
    amplitude = 10 ** (dbfs / 20)
    return (amplitude * np.sign(np.sin(np.arange(windows * VOICE_WINDOW) + 0.5))).astype(np.float32)


def test_the_background_is_the_level_of_the_sound_that_is_not_speech() -> None:
    mono = np.concatenate([_level(-20.0, 10), _level(-5.0, 10)])
    voice = np.array([0.0] * 10 + [0.9] * 10, dtype=np.float32)  # the loud half is speech
    assert background_dbfs(mono, voice) == pytest.approx(-20.0, abs=0.01)


def test_silence_is_not_background() -> None:
    mono = np.concatenate([np.zeros(10 * VOICE_WINDOW, np.float32), _level(-30.0, 5)])
    assert background_dbfs(mono, np.zeros(15, np.float32)) == pytest.approx(-30.0, abs=0.01)


def test_a_chunk_of_only_speech_or_silence_has_no_background() -> None:
    mono = _level(-10.0, 4)
    assert background_dbfs(mono, np.ones(4, np.float32)) == -120.0
    assert background_dbfs(mono, np.ones(4, np.float32)) < SEPARATION_BED_DBFS


# ---- files and the merge -------------------------------------------------------------------------


def test_a_window_is_written_as_16_bit_pcm(tmp_path: Path) -> None:
    samples = np.array([[0.5, -0.5], [2.0, -2.0]], dtype=np.float32)  # out of range is clipped
    write_wav(tmp_path / "w.wav", samples, 48000)
    with wave.open(str(tmp_path / "w.wav")) as wav:
        assert (wav.getnchannels(), wav.getsampwidth(), wav.getframerate()) == (2, 2, 48000)
        pcm = np.frombuffer(wav.readframes(2), dtype="<i2")
    assert pcm.tolist() == [16383, -16383, 32767, -32767]


def test_a_stem_is_fitted_to_the_chunk_audio() -> None:
    stem = np.arange(5, dtype=np.float32)
    assert _fit(stem, 3).tolist() == [0, 1, 2]
    assert _fit(stem, 7).tolist() == [0, 1, 2, 3, 4, 0, 0]
