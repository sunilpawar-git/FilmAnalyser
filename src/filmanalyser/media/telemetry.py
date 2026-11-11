"""Memory measurement for the per-chunk log events (`core.events` formats and emits them)."""

import resource
import sys

_RSS_UNIT = 1024 * 1024 if sys.platform == "darwin" else 1024  # ru_maxrss: bytes vs kilobytes


def peak_rss_mb() -> float:
    """Peak resident set size of this process so far, in megabytes."""
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / _RSS_UNIT
