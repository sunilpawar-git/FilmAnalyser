"""Memory measurement for the per-chunk log events (`core.events` formats and emits them)."""

import resource
import sys
from pathlib import Path

_RSS_UNIT = 1024 * 1024 if sys.platform == "darwin" else 1024  # ru_maxrss: bytes vs kilobytes
_STATUS = Path("/proc/self/status")  # Linux only


def parse_vm_hwm(text: str) -> float | None:
    """The `VmHWM` line of /proc/self/status (peak resident size, kB) in megabytes, if present."""
    for line in text.splitlines():
        if line.startswith("VmHWM:"):
            return int(line.split()[1]) / 1024
    return None


def peak_rss_mb() -> float:
    """Peak resident set size of this program so far, in megabytes.

    On Linux this is `VmHWM`, the peak of this program's own memory. `ru_maxrss` is not used there:
    Linux carries it over when a process starts a new program, so a child started from a large
    process reported its parent's peak (the memory test's worker read 860 MB, its own peak being
    about 50 MB). Elsewhere (macOS) `ru_maxrss` is the program's own."""
    try:
        own = parse_vm_hwm(_STATUS.read_text(encoding="ascii"))
    except OSError:
        own = None
    if own is not None:
        return own
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / _RSS_UNIT
