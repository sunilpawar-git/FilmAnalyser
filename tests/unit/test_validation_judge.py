"""The validation rules: tolerance, nearest-match, the climax, the budgets, the kill/pivot rule."""

import pytest

from validation_judge import (
    Expected,
    Measured,
    Verdict,
    breaks_matched,
    judge,
    pivot_required,
)

TOL = 300.0


def _measured(breaks: tuple[float, ...] = (), peak: float | None = None) -> Measured:
    return Measured(breaks, peak, 1000.0, 1000.0)


def test_a_break_inside_the_tolerance_matches_and_one_outside_does_not() -> None:
    assert breaks_matched((1000.0,), (1300.0,), TOL) == 1  # exactly on the edge counts
    assert breaks_matched((1000.0,), (1300.1,), TOL) == 0


def test_one_detected_break_serves_one_expected_break_only() -> None:
    assert breaks_matched((1000.0,), (900.0, 1100.0), TOL) == 1
    assert breaks_matched((1000.0, 1150.0), (900.0, 1100.0), TOL) == 2


def test_the_nearest_detected_break_is_used_first() -> None:
    assert breaks_matched((1500.0, 1100.0), (1000.0, 1400.0), TOL) == 2


def test_no_detected_breaks_match_nothing() -> None:
    assert breaks_matched((), (1000.0,), TOL) == 0


def test_a_film_passes_when_every_expected_break_is_found() -> None:
    verdict = judge(_measured((1000.0, 5000.0)), Expected((1100.0, 5200.0), None), TOL, TOL)
    assert verdict.breaks_ok is True and verdict.breaks_found == 2
    assert verdict.climax_ok is None  # no climax given: no verdict


def test_a_film_misses_when_one_expected_break_is_not_found() -> None:
    verdict = judge(_measured((1000.0,)), Expected((1100.0, 5200.0), None), TOL, TOL)
    assert verdict.breaks_ok is False and verdict.breaks_found == 1


def test_no_expected_breaks_gives_no_verdict() -> None:
    assert judge(_measured(), Expected((), None), TOL, TOL).breaks_ok is None


def test_the_tension_peak_must_be_near_the_climax() -> None:
    near = judge(_measured(peak=6000.0), Expected((), 6200.0), TOL, TOL)
    far = judge(_measured(peak=3000.0), Expected((), 6200.0), TOL, TOL)
    none = judge(_measured(peak=None), Expected((), 6200.0), TOL, TOL)
    assert (near.climax_ok, far.climax_ok, none.climax_ok) == (True, False, False)


def test_the_budgets_are_two_gigabytes_and_forty_five_minutes() -> None:
    within = judge(Measured((), None, 2047.0, 2699.0), Expected((), None), TOL, TOL)
    over = judge(Measured((), None, 2048.0, 2700.0), Expected((), None), TOL, TOL)
    unmeasured = judge(Measured((), None, None, None), Expected((), None), TOL, TOL)
    assert (within.ram_ok, within.runtime_ok) == (True, True)
    assert (over.ram_ok, over.runtime_ok) == (False, False)
    assert (unmeasured.ram_ok, unmeasured.runtime_ok) == (None, None)


def _verdict(ok: bool | None) -> Verdict:
    return Verdict(0, 2, ok, None, None, None)


@pytest.mark.parametrize(
    ("oks", "expected"),
    [
        ([False, False, True], True),
        ([False, False, False], True),
        ([False, True, True], False),
        ([True, True, True], False),
        ([False, False], None),  # fewer than three films: the rule cannot be applied yet
        ([False, False, None], None),  # a film with no expected breaks does not count
    ],
)
def test_the_kill_pivot_rule_fires_on_two_misses_in_three_films(
    oks: list[bool | None], expected: bool | None
) -> None:
    assert pivot_required([_verdict(ok) for ok in oks]) is expected
