"""A stand-in for the `demucs` command, so the separation path runs in CI without PyTorch.

It reads the arguments the pipeline passes (`-o OUT ... -- INPUT...`) and, for each input, writes
`OUT/htdemucs/<name>.vocals.wav`: the file named by FAKE_STEM (16 kHz mono WAV) repeated to the
input's length. FAKE_FAIL makes it exit 3; FAKE_SLEEP makes it wait first; FAKE_LOG gets one line
per run listing its inputs."""

import os
import sys
import time
import wave
from pathlib import Path


def _write_stem(source: Path, length_s: float, target: Path) -> None:
    with wave.open(str(source)) as wav:
        rate, frames = wav.getframerate(), wav.readframes(wav.getnframes())
    need = round(length_s * rate) * 2
    data = (frames * (need // max(len(frames), 1) + 1))[:need]
    with wave.open(str(target), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(rate)
        out.writeframes(data)


def main(argv: list[str]) -> int:
    time.sleep(float(os.environ.get("FAKE_SLEEP", "0")))
    if os.environ.get("FAKE_FAIL"):
        print("fake demucs failed", file=sys.stderr)
        return 3
    out = Path(argv[argv.index("-o") + 1]) / argv[argv.index("-n") + 1]
    inputs = [Path(item) for item in argv[argv.index("--") + 1 :]]
    if "FAKE_LOG" in os.environ:
        with open(os.environ["FAKE_LOG"], "a", encoding="utf-8") as log:
            log.write(" ".join(item.name for item in inputs) + "\n")
    out.mkdir(parents=True, exist_ok=True)
    for item in inputs:
        with wave.open(str(item)) as wav:
            length_s = wav.getnframes() / wav.getframerate()
        _write_stem(Path(os.environ["FAKE_STEM"]), length_s, out / f"{item.stem}.vocals.wav")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
