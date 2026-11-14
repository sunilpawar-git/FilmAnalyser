"""The rules of the real-film validation (ACCEPTANCE.md, Validity and Performance), as pure
functions: do the detected act breaks fall within the tolerance of the owner's, is the tension
peak near the climax, are the budgets met, and does the kill/pivot rule fire. No I/O, so the rules
are tested without a film. The numbers it judges come from `validate_real_film.py`."""

from dataclasses import dataclass

RAM_LIMIT_MB = 2048.0  # ACCEPTANCE: peak RAM < 2 GB
RUNTIME_LIMIT_S = 45 * 60.0  # ACCEPTANCE: full run < 45 min
PIVOT_MISSES = 2  # kill/pivot: act-break detection misses on 2 of 3 films
PIVOT_FILMS = 3


@dataclass(frozen=True)
class Measured:
    """What one run produced (None where it was not measured or not found)."""

    detected_breaks_s: tuple[float, ...]
    peak_s: float | None  # the tension peak, None when none reached the reporting height
    peak_ram_mb: float | None
    runtime_s: float | None


@dataclass(frozen=True)
class Expected:
    """What the owner says is true of the film. Never AI-estimated (DECISIONS #94)."""

    act_breaks_s: tuple[float, ...]
    climax_s: float | None


@dataclass(frozen=True)
class Verdict:
    breaks_found: int
    breaks_expected: int
    breaks_ok: bool | None  # None: no expected breaks were given
    climax_ok: bool | None  # None: no climax was given
    ram_ok: bool | None  # None: not measured
    runtime_ok: bool | None


def breaks_matched(detected: tuple[float, ...], expected: tuple[float, ...], tol_s: float) -> int:
    """How many expected breaks have a detected break within `tol_s`; each detected break serves
    one expected break only (the nearest first)."""
    free = list(detected)
    matched = 0
    for target in sorted(expected):
        near = [d for d in free if abs(d - target) <= tol_s]
        if near:
            free.remove(min(near, key=lambda d: abs(d - target)))
            matched += 1
    return matched


def judge(measured: Measured, expected: Expected, tol_s: float, climax_tol_s: float) -> Verdict:
    found = breaks_matched(measured.detected_breaks_s, expected.act_breaks_s, tol_s)
    wanted = len(expected.act_breaks_s)
    climax: bool | None = None
    if expected.climax_s is not None:
        climax = measured.peak_s is not None and abs(measured.peak_s - expected.climax_s) <= (
            climax_tol_s
        )
    return Verdict(
        breaks_found=found,
        breaks_expected=wanted,
        breaks_ok=None if wanted == 0 else found == wanted,
        climax_ok=climax,
        ram_ok=None if measured.peak_ram_mb is None else measured.peak_ram_mb < RAM_LIMIT_MB,
        runtime_ok=None if measured.runtime_s is None else measured.runtime_s < RUNTIME_LIMIT_S,
    )


def pivot_required(development: list[Verdict]) -> bool | None:
    """The kill/pivot rule over the development films (not the held-out one): True when
    act-break detection missed on 2 of 3. None until three development films have an answer."""
    answered = [v for v in development if v.breaks_ok is not None]
    if len(answered) < PIVOT_FILMS:
        return None
    return sum(1 for v in answered if not v.breaks_ok) >= PIVOT_MISSES
