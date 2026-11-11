"""Child process for the memory-flatness test: decode a film, discard every chunk, report RSS.
A fresh process per film keeps the peak-RSS figure honest (it cannot inherit earlier runs)."""

import json
import sys

from filmanalyser.core.config import Config
from filmanalyser.media.ffmpeg_stream import decode_chunks
from filmanalyser.media.telemetry import peak_rss_mb


def main(path: str, chunk_seconds: float) -> None:
    config = Config(chunk_seconds=chunk_seconds, overlap_seconds=1.0, analysis_fps=10.0)
    chunks = frames = 0
    for chunk in decode_chunks(path, config):
        chunks += 1
        frames += len(chunk.core)
    print(json.dumps({"chunks": chunks, "frames": frames, "peak_rss_mb": peak_rss_mb()}))


if __name__ == "__main__":
    main(sys.argv[1], float(sys.argv[2]))
