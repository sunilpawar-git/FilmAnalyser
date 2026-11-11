"""Structured logging and memory measurement.

One JSON object per event. Fields are scalars only (film content, arrays and containers are
refused) and any string is reduced to its basename, so logs can never carry film content or
full paths (Improvement 10). Handlers and levels are the CLI's business, not the library's.
"""

import json
import logging
import resource
import sys
from collections.abc import Mapping

LOGGER = logging.getLogger("filmanalyser")
_RSS_UNIT = 1024 * 1024 if sys.platform == "darwin" else 1024  # ru_maxrss: bytes vs kilobytes


def peak_rss_mb() -> float:
    """Peak resident set size of this process so far, in megabytes."""
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / _RSS_UNIT


def _clean(value: str | int | float | bool) -> str | int | float | bool:
    if isinstance(value, bool | int | float):
        return value
    if isinstance(value, str):
        return value.replace("\\", "/").rsplit("/", 1)[-1]
    raise TypeError("log fields must be scalar (str, int, float, bool)")


def format_event(event: str, fields: Mapping[str, str | int | float | bool]) -> str:
    if "event" in fields:
        raise ValueError("'event' is reserved for the event name")
    return json.dumps({"event": event, **{k: _clean(v) for k, v in fields.items()}})


def log_event(event: str, **fields: str | int | float | bool) -> None:
    LOGGER.info(format_event(event, fields))
