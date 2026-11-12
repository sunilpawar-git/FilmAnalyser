"""Kill-and-resume harness shared by the synthetic and real-clip tests: run a worker process
(`tests.integration._resume_worker`) over a film, SIGKILL it after N stored chunks, resume it.
Every worker has a watchdog so a hung process fails the test, and a finished test never waits."""

import signal
import subprocess
import sys
import threading
from pathlib import Path

import pytest

from tests.architecture._scan import REPO

WATCHDOG_S = 1800  # generous: a real clip is slow; a hung worker must still fail the run


def start(film: Path, directory: Path, gate: int, profile: str) -> subprocess.Popen[str]:
    argv = [sys.executable, "-m", "tests.integration._resume_worker", str(film), str(directory)]
    proc = subprocess.Popen(
        [*argv, str(gate), profile],
        cwd=REPO,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    watchdog = threading.Timer(WATCHDOG_S, proc.kill)
    watchdog.daemon = True  # a finished test must not wait for it
    watchdog.start()
    return proc


def run_until_killed(
    film: Path, directory: Path, gate: int, profile: str = "synthetic"
) -> list[str]:
    """Run a worker until it has stored `gate` chunks, then SIGKILL it; return its output."""
    proc = start(film, directory, gate, profile)
    assert proc.stdout is not None
    lines: list[str] = []
    for line in proc.stdout:
        lines.append(line.strip())
        if line.strip() == f"gate {gate}":
            break
    else:
        pytest.fail(f"worker ended before the gate: {lines} {proc.communicate()[1]}")
    proc.send_signal(signal.SIGKILL)
    assert proc.wait() == -signal.SIGKILL  # killed for real, not exited
    return lines


def run_to_end(film: Path, directory: Path, profile: str = "synthetic") -> list[str]:
    proc = start(film, directory, 0, profile)
    out, err = proc.communicate(input="")
    assert proc.returncode == 0, err
    return out.split()


def decoded(lines: list[str]) -> list[int]:
    words = " ".join(lines).split()
    return [int(words[i + 1]) for i, w in enumerate(words) if w == "decoded"]
