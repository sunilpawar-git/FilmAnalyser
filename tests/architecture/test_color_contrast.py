"""Accessibility: colour tokens meet WCAG AA contrast in both themes."""

import pytest
from hypothesis import given
from hypothesis import strategies as st

from filmanalyser.report.resources.colors import (
    CONTRAST_RULES,
    ColorTokens,
    ContrastRule,
    contrast_ratio,
)

TOKENS = ColorTokens.load()


@pytest.mark.parametrize("theme", ["light", "dark"])
@pytest.mark.parametrize("rule", CONTRAST_RULES, ids=lambda r: f"{r.foreground}-on-{r.background}")
def test_pair_meets_minimum_contrast(theme: str, rule: ContrastRule) -> None:
    palette = TOKENS.theme(theme)
    ratio = contrast_ratio(palette[rule.foreground], palette[rule.background])
    assert ratio >= rule.minimum, f"{theme}: {ratio:.2f} < {rule.minimum}"


def test_every_rule_references_existing_tokens() -> None:
    names = set(TOKENS.theme("light"))
    assert all({r.foreground, r.background} <= names for r in CONTRAST_RULES)


def test_black_on_white_is_21() -> None:
    assert contrast_ratio("#000000", "#ffffff") == pytest.approx(21.0)


def test_identical_colors_have_ratio_1() -> None:
    assert contrast_ratio("#336699", "#336699") == pytest.approx(1.0)


@given(
    st.from_regex(r"#[0-9a-f]{6}", fullmatch=True), st.from_regex(r"#[0-9a-f]{6}", fullmatch=True)
)
def test_contrast_is_symmetric_and_at_least_one(a: str, b: str) -> None:
    assert contrast_ratio(a, b) == pytest.approx(contrast_ratio(b, a))
    assert contrast_ratio(a, b) >= 1.0
