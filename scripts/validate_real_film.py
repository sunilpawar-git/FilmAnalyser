"""Real-film validation (ACCEPTANCE.md, Phase 8): `python scripts/validate_real_film.py TRUTH.json`.

TRUTH.json is written by the owner, outside the repo, for films they know:
  {"verified_by": "owner", "tolerance_s": 300, "climax_tolerance_s": 300,
   "films": [{"title": "...", "film": "/abs/film.mp4", "out": "/abs/store-dir",
              "held_out": false, "act_breaks_s": [1800, 5400], "climax_s": 6300}, ...]}
Each film is run through the real command in its own process (so peak memory and run time are that
run's own), then analysed and judged by `validation_judge`. The output is a Markdown table to paste
into the handoff. Times in the file must be the owner's own (DECISIONS #94): the file is refused
unless it says `"verified_by": "owner"` (a file with no times, for memory and run time only, needs
no attestation). `--keep` resumes an existing store instead of starting
fresh; memory and run time are then not measured, because a resumed run does not extract.
"""

import json
import os
import platform
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from filmanalyser.analysis.act_breaks import find_act_breaks
from filmanalyser.analysis.tension import analyse_tension
from filmanalyser.analysis.timeline import build_timeline
from filmanalyser.report.display import clock_text
from timeline_report import read_store
from validation_judge import Expected, Measured, Verdict, judge, pivot_required

DEFAULT_TOLERANCE_S = 300.0  # ACCEPTANCE: within +-5 min
BYTES_PER_MB = 1024 * 1024
KB_PER_MB = 1024


@dataclass(frozen=True)
class FilmCase:
    title: str
    film: Path
    out: Path
    held_out: bool
    expected: Expected


def load_cases(text: str) -> tuple[list[FilmCase], float, float]:
    """The films and tolerances of a truth file; ValueError when it is not the owner's."""
    data = json.loads(text)
    has_times = any(item.get("act_breaks_s") or item.get("climax_s") for item in data["films"])
    if has_times and data.get("verified_by") != "owner":
        raise ValueError('refused: times need "verified_by": "owner" in the truth file (#94)')
    tol = float(data.get("tolerance_s", DEFAULT_TOLERANCE_S))
    climax_tol = float(data.get("climax_tolerance_s", tol))
    cases = [
        FilmCase(
            title=str(item["title"]),
            film=Path(item["film"]),
            out=Path(item["out"]),
            held_out=bool(item.get("held_out", False)),
            expected=Expected(
                tuple(float(t) for t in item.get("act_breaks_s", [])),
                None if item.get("climax_s") is None else float(item["climax_s"]),
            ),
        )
        for item in data["films"]
    ]
    return cases, tol, climax_tol


def peak_mb(ru_maxrss: int, system: str) -> float:
    """ru_maxrss is bytes on macOS and kilobytes elsewhere."""
    return ru_maxrss / (BYTES_PER_MB if system == "Darwin" else KB_PER_MB)


def run_command(case: FilmCase, *, fresh: bool) -> tuple[int, float, float]:
    """Run the real command in its own process: (exit code, seconds, peak MB of that process and
    everything it started, ffmpeg included)."""
    tool = Path(sys.executable).with_name("filmanalyser")  # the installed command, same environment
    argv = [
        str(tool),
        "--out",
        str(case.out),
        *(["--fresh"] if fresh else []),
        "--",
        str(case.film),
    ]
    began = time.perf_counter()
    child = subprocess.Popen(argv, stdout=subprocess.DEVNULL)
    _, status, usage = os.wait4(child.pid, 0)
    child.returncode = os.waitstatus_to_exitcode(status)
    return (
        child.returncode,
        time.perf_counter() - began,
        peak_mb(usage.ru_maxrss, platform.system()),
    )


def analyse_store(out: Path) -> tuple[tuple[float, ...], float | None, float]:
    """(detected act-break times, tension peak time, film length) of a finished store."""
    timeline = build_timeline(read_store(out))
    peak = analyse_tension(timeline).peak
    breaks = tuple(b.time_s for b in find_act_breaks(timeline).breaks)
    return breaks, None if peak is None else peak.start_s, timeline.film_end_s


def machine() -> str:
    """Chip and memory, for ACCEPTANCE's 'record chip + RAM'."""
    chip = platform.processor() or platform.machine()
    pages = os.sysconf("SC_PHYS_PAGES") * os.sysconf("SC_PAGE_SIZE")
    return f"{platform.system()} {platform.machine()} ({chip}), {pages / 1024**3:.0f} GB RAM"


def _mark(value: bool | None) -> str:
    return "n/a" if value is None else ("yes" if value else "NO")


def row(case: FilmCase, measured: Measured, film_s: float, verdict: Verdict) -> str:
    peak = "none" if measured.peak_s is None else clock_text(measured.peak_s)
    ram = "not measured" if measured.peak_ram_mb is None else f"{measured.peak_ram_mb:.0f} MB"
    took = "not measured" if measured.runtime_s is None else clock_text(measured.runtime_s)
    breaks = ", ".join(clock_text(t) for t in measured.detected_breaks_s) or "none"
    return (
        f"| {case.title}{' (held out)' if case.held_out else ''} | {clock_text(film_s)} | {ram} "
        f"({_mark(verdict.ram_ok)}) | {took} ({_mark(verdict.runtime_ok)}) | {breaks} | "
        f"{verdict.breaks_found}/{verdict.breaks_expected} ({_mark(verdict.breaks_ok)}) | {peak} "
        f"({_mark(verdict.climax_ok)}) |"
    )


HEADER = (
    "| Film | Length | Peak RAM (< 2 GB) | Run time (< 45 min) | Detected breaks | "
    "Expected breaks found | Tension peak (near climax) |\n|---|---|---|---|---|---|---|"
)


def validate(cases: list[FilmCase], tol: float, climax_tol: float, *, fresh: bool) -> list[str]:
    lines = [
        f"Machine: {machine()}",
        f"Tolerance: {tol:.0f} s (climax {climax_tol:.0f} s)",
        "",
        HEADER,
    ]
    development: list[Verdict] = []
    for case in cases:
        code, seconds, ram = run_command(case, fresh=fresh)
        if code != 0:
            lines.append(f"| {case.title} | the command exited with code {code} | | | | | |")
            continue
        breaks, peak, film_s = analyse_store(case.out)
        measured = Measured(breaks, peak, ram if fresh else None, seconds if fresh else None)
        verdict = judge(measured, case.expected, tol, climax_tol)
        lines.append(row(case, measured, film_s, verdict))
        if not case.held_out:
            development.append(verdict)
    pivot = pivot_required(development)
    lines += ["", f"Kill/pivot rule (misses on 2 of 3 development films): {_pivot_text(pivot)}"]
    return lines


def _pivot_text(pivot: bool | None) -> str:
    if pivot is None:
        return "not applicable yet (needs three development films with expected breaks)"
    return "FIRES: change the approach" if pivot else "does not fire"


def main(argv: list[str]) -> int:
    keep = "--keep" in argv
    paths = [a for a in argv[1:] if a != "--keep"]
    if len(paths) != 1:
        print(__doc__)
        return 2
    try:
        cases, tol, climax_tol = load_cases(Path(paths[0]).read_text(encoding="utf-8"))
    except (ValueError, KeyError, OSError) as exc:
        print(f"validate_real_film: {exc}", file=sys.stderr)
        return 1
    print("\n".join(validate(cases, tol, climax_tol, fresh=not keep)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
