"""Prove the guards work: plant each deliberate violation, run the relevant check, require a
failure for the stated reason, then remove the violation. Exit 1 if any guard stays silent."""

import subprocess
import sys
from pathlib import Path

from guard_probes import Probe, other_probes, source_probes

REPO = Path(__file__).resolve().parents[1]
TIMEOUT_SECONDS = 300


def run_probe(probe: Probe) -> str | None:
    """None when the guard caught the violation; otherwise a description of what went wrong."""
    target = REPO / probe.path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(probe.content, encoding="utf-8")
    try:
        done = subprocess.run(
            probe.command,
            cwd=REPO,
            check=False,
            capture_output=True,
            text=True,
            timeout=TIMEOUT_SECONDS,
        )
    finally:
        target.unlink(missing_ok=True)
    output = done.stdout + done.stderr
    if done.returncode == 0:
        return "check PASSED with the violation present (guard is silent)"
    if probe.expect not in output:
        return f"check failed, but not for the expected reason ({probe.expect!r} not in output)"
    return None


def main() -> int:
    failures = 0
    for probe in [*source_probes(), *other_probes()]:
        problem = run_probe(probe)
        status = "caught" if problem is None else f"NOT CAUGHT: {problem}"
        print(f"  {'ok  ' if problem is None else 'FAIL'} {probe.name}: {status}")
        failures += problem is not None
    print(f"guard self-test: {failures} failing guard(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
