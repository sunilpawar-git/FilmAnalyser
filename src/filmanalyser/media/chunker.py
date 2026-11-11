"""Group a stream of frames into overlapping chunks, holding one chunk in memory at a time."""

from collections.abc import Iterable, Iterator

import numpy as np

from filmanalyser.core.chunk import Chunk, Frames, span_for
from filmanalyser.core.config import Config


def _fill(buf: Frames, start: int, source: Iterator[Frames], shape: tuple[int, int]) -> int:
    """Copy frames from `source` into buf[start:], returning how many were read."""
    count = 0
    for slot in range(start, len(buf)):
        frame = next(source, None)
        if frame is None:
            break
        if frame.shape != (*shape, 3):
            raise ValueError(f"unexpected frame shape {frame.shape}, wanted {(*shape, 3)}")
        buf[slot] = frame
        count += 1
    return count


def chunk_frames(
    frames: Iterable[Frames], config: Config, shape: tuple[int, int], first_index: int = 0
) -> Iterator[Chunk]:
    """Cut `frames` (each (height, width, 3) uint8) into chunks of `config.frames_per_chunk`
    frames. Every chunk after the first begins with the last `config.overlap_frames` frames of
    its predecessor. Only the final chunk may be short. Frames are read lazily: when a chunk is
    yielded, no later frame has been requested, so only one chunk is ever in memory.

    A resumed run passes `first_index` > 0 and a stream that begins at that chunk's context start
    (see `span_for`): the first chunk then reads its own context from the stream instead of
    carrying it from a predecessor, and is identical to the one an uninterrupted run produces."""
    per_chunk, overlap, fps = config.frames_per_chunk, config.overlap_frames, config.analysis_fps
    source = iter(frames)
    tail = np.empty((0, *shape, 3), dtype=np.uint8)
    index = first_index
    while True:
        span = span_for(index, per_chunk, overlap)
        context = span.context_len
        buf = np.empty((context + per_chunk, *shape, 3), dtype=np.uint8)
        carried = context if index > first_index else 0  # the resumed first chunk has no tail
        buf[:carried] = tail[:carried]
        used = carried + _fill(buf, carried, source, shape)
        read = used - context  # core frames; <= 0 means the stream ended inside the context
        if read <= 0:
            return
        tail = buf[used - overlap : used].copy() if overlap else tail[:0]
        yield Chunk(
            index, span.core_start / fps, (span.core_start + read) / fps, fps, buf[:used], context
        )
        if read < per_chunk:
            return
        index += 1
