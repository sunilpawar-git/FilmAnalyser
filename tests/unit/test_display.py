"""Display text: digits, a point and a colon only, never a locale."""

from filmanalyser.report.display import clock_text, number_text


def test_clock_text_is_digits_with_a_colon_and_no_locale() -> None:
    assert clock_text(0.0) == "0:00"
    assert clock_text(780.0) == "13:00"
    assert clock_text(59.9) == "0:59"  # truncated, never rounded up to the next minute
    assert clock_text(3661.0) == "1:01:01"
    assert clock_text(10 * 3600.0) == "10:00:00"


def test_number_text_has_a_fixed_number_of_decimals_and_a_point() -> None:
    assert number_text(1.0) == "1.0"
    assert number_text(1.5, 2) == "1.50"
    assert number_text(1234.5678, 0) == "1235"


def test_a_value_that_rounds_to_zero_has_no_minus_sign() -> None:
    assert number_text(-0.04) == "0.0"
    assert number_text(-0.4, 0) == "0"
    assert number_text(-0.5) == "-0.5"
