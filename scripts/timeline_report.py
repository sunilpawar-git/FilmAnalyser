"""Print the timeline analysis of a stored run: `python scripts/timeline_report.py STORE_DIR`.

Reads the store's own files (each verified against the manifest's hash), builds the timeline and
prints act breaks, tension peak, pacing plateaus and flags as observations. It reports what the
numbers say; there is no ground truth for act structure, so nothing here is called "correct".
"""

import io
import sys
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from filmanalyser.analysis.act_breaks import find_act_breaks
from filmanalyser.analysis.flags import find_flags
from filmanalyser.analysis.pacing import analyse_pacing
from filmanalyser.analysis.tension import analyse_tension
from filmanalyser.analysis.timeline import Columns, build_timeline
from filmanalyser.core.config import STORE_MAX_FILE_BYTES
from filmanalyser.core.errors import StorageError
from filmanalyser.storage.files import read_bounded, sha256_bytes
from filmanalyser.storage.manifest import load_manifest
from filmanalyser.storage.schema import chunk_file_name


def read_store(root: Path) -> Columns:
    """Every chunk of a finished store as one array per column; a damaged chunk raises."""
    manifest = load_manifest(root)
    if manifest is None or not manifest.complete:
        raise StorageError(key="error.storage.default", name=root.name)
    tables = []
    for index, digest in enumerate(manifest.chunks):
        data = read_bounded(
            root, chunk_file_name(index), STORE_MAX_FILE_BYTES, "error.storage.chunk_corrupt"
        )
        if sha256_bytes(data) != digest:
            raise StorageError(key="error.storage.chunk_corrupt", name=chunk_file_name(index))
        tables.append(pq.read_table(io.BytesIO(data)))
    whole = pa.concat_tables(tables)
    return {name: whole.column(name).to_numpy() for name in whole.column_names}


def clock(seconds: float) -> str:
    whole = int(seconds)
    return f"{whole // 3600}:{whole % 3600 // 60:02d}:{whole % 60:02d}"


def describe(columns: Columns) -> list[str]:
    timeline = build_timeline(columns)
    acts, tension, pacing = (
        find_act_breaks(timeline),
        analyse_tension(timeline),
        analyse_pacing(timeline),
    )
    lines = [
        f"film {clock(timeline.film_end_s)}, {timeline.count} chunks, audio: {acts.audio_used}",
        f"boundaries scored: {acts.scored}; features: {', '.join(acts.features_used)}",
    ]
    lines += [
        f"act break at {clock(b.time_s)} (boundary {b.boundary}, "
        f"{100 * b.time_s / timeline.film_end_s:.0f}% of the film), score {b.score:.2f}, "
        f"moved most: {', '.join(b.moved)}"
        for b in acts.breaks
    ]
    lines += [f"no break in zone {zone}" for zone in acts.empty_zones]
    peak = tension.peak
    lines.append(
        f"tension peak at {clock(peak.start_s)} (z {peak.value:.2f}; "
        f"{', '.join(tension.components)})"
        if peak
        else "no tension peak above the minimum height"
    )
    lines.append(
        f"mean cut rate {pacing.mean_rate:.2f} per minute; {len(pacing.plateaus)} plateaus"
    )
    lines += [
        f"plateau {clock(p.start_s)} to {clock(p.end_s)} at {p.mean_rate:.2f} cuts per minute"
        for p in pacing.plateaus
    ]
    flags = find_flags(timeline)
    kinds = sorted({flag.kind.value for flag in flags})
    lines.append(
        f"{len(flags)} flags: " + ", ".join(f"{k} {sum(x.kind == k for x in flags)}" for k in kinds)
    )
    return lines


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__)
        return 2
    print("\n".join(describe(read_store(Path(argv[1])))))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
