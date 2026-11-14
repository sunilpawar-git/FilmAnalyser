"""Display-ready text from numbers: ASCII digits, a point and a colon only, never a locale.

Pure. The words around a value live in strings.toml; this module only writes the value itself.
"""

SECONDS_PER_MINUTE = 60
SECONDS_PER_HOUR = 3600


def number_text(value: float, decimals: int = 1) -> str:
    """`value` with a fixed number of decimals and a point; a value that rounds to zero is 0."""
    text = f"{value:.{decimals}f}"
    return text.removeprefix("-") if float(text) == 0.0 else text


def clock_text(seconds: float) -> str:
    """Film time as M:SS, or H:MM:SS from one hour on. Whole seconds, truncated."""
    whole = max(int(seconds), 0)
    hours, rest = divmod(whole, SECONDS_PER_HOUR)
    minutes, secs = divmod(rest, SECONDS_PER_MINUTE)
    return f"{hours}:{minutes:02d}:{secs:02d}" if hours else f"{minutes}:{secs:02d}"
