"""Names that the report's data and its resources share, defined once (SSOT): the strings.toml key
each value is looked up under, and the CSS class each chart element carries. The view model builds
keys with these, and a test checks that every one resolves."""

SERIES_STYLES = (
    "s1",
    "s2",
    "s3",
    "s4",
)  # a colour and a dash pattern each (templates/partials/style.html)
MARK_BREAK = "break"  # a vertical marker for an act break
MARK_PEAK = "peak"  # a vertical marker for the tension peak
MARK_BAND = "band"  # a shaded stretch (the legend swatch of a pacing plateau)


def feature_key(name: str) -> str:
    """The key that labels a feature column (`color.brightness`) or derived series (`cut_rate`)."""
    return f"feature.{name}"


def flag_kind_key(kind: str) -> str:
    return f"flag.kind.{kind}"


def flag_value_key(kind: str) -> str:
    return f"flag.value.{kind}"
