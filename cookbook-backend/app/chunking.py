"""Chunking strategies.

`chunk_document` is the entry point; `chunk_strategy` in settings picks one:

- **recursive** (default): split on the largest structural separator that fits
  (paragraph, then line, then sentence, then word), recurse into any piece
  still too big, then pack neighbouring pieces up to `chunk_size` with
  `chunk_overlap` carried between them. Respects document structure and costs
  nothing.
- **semantic**: embed each sentence with its neighbours and cut where the
  cosine distance between consecutive sentences spikes past a percentile.
  Splits on meaning rather than shape, at the price of an embedding call per
  sentence.
- **character**: fixed-size windows. Cheap, structure-blind, and the last
  resort when the others fail.
"""

import logging
import math
import re

from app.config import settings

logger = logging.getLogger(__name__)

# Sentence end (. ! ?, optionally closed by a quote or bracket) or a blank line.
# Two fixed-width lookbehinds, because `re` rejects a variable-width one.
_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+|(?<=[.!?][\"')\]])\s+|\n\s*\n")

# Tried in order, largest structural unit first. The final "" splits between
# characters, so even a single unbroken word can be cut down to size.
SEPARATORS = ["\n\n", "\n", ". ", "! ", "? ", "; ", ", ", " ", ""]

# Gemini's embedding endpoint caps how many texts one request may carry.
EMBED_BATCH_SIZE = 100


# --------------------------------------------------------------------------
# character
# --------------------------------------------------------------------------


def chunk_text(text: str, chunk_size: int = 1000, chunk_overlap: int = 150) -> list[str]:
    """Fixed-size character chunker. The floor every other strategy falls back to."""
    text = text.strip()
    if not text:
        return []
    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunks.append(text[start:end])
        if end >= len(text):
            break
        start = end - chunk_overlap
    return chunks


# --------------------------------------------------------------------------
# recursive
# --------------------------------------------------------------------------


def _pick_separator(text: str, separators: list[str]) -> tuple[str, list[str]]:
    """First separator that occurs in the text, plus the ones left to try after it."""
    for i, separator in enumerate(separators):
        if separator == "" or separator in text:
            return separator, separators[i + 1 :]
    return separators[-1], []


def _merge(pieces: list[str], separator: str, size: int, overlap: int) -> list[str]:
    """Pack consecutive pieces into chunks of at most `size`, overlapping by `overlap`.

    Pieces are already small enough individually; this is what stops a document
    being shattered into one chunk per line.
    """
    merged: list[str] = []
    window: list[str] = []
    length = 0

    def joined_length(extra: int, count: int) -> int:
        return length + extra + (len(separator) if count else 0)

    for piece in pieces:
        if not piece:
            continue
        if window and joined_length(len(piece), len(window)) > size:
            merged.append(separator.join(window))
            # Drop from the front until the carried-over tail fits the overlap budget
            # and the incoming piece fits the size budget.
            while window and (
                length > overlap or joined_length(len(piece), len(window)) > size
            ):
                length -= len(window[0]) + (len(separator) if len(window) > 1 else 0)
                window.pop(0)
        window.append(piece)
        length += len(piece) + (len(separator) if len(window) > 1 else 0)

    if window:
        merged.append(separator.join(window))
    return [chunk for chunk in (chunk.strip() for chunk in merged) if chunk]


def _split_recursive(text: str, separators: list[str], size: int, overlap: int) -> list[str]:
    separator, remaining = _pick_separator(text, separators)
    pieces = list(text) if separator == "" else text.split(separator)

    chunks: list[str] = []
    pending: list[str] = []
    for piece in pieces:
        if len(piece) <= size:
            pending.append(piece)
            continue
        # Too big for this separator: flush what we have, then try a finer one.
        chunks.extend(_merge(pending, separator, size, overlap))
        pending = []
        if remaining:
            chunks.extend(_split_recursive(piece, remaining, size, overlap))
        else:
            chunks.extend(chunk_text(piece, size, overlap))
    chunks.extend(_merge(pending, separator, size, overlap))
    return chunks


def recursive_chunk_text(
    text: str,
    chunk_size: int | None = None,
    chunk_overlap: int | None = None,
    separators: list[str] | None = None,
) -> list[str]:
    """Split on the largest separator that keeps chunks under `chunk_size`."""
    text = text.strip()
    if not text:
        return []
    size = chunk_size or settings.chunk_size
    # An overlap at or above the chunk size would never let the window shrink.
    overlap = min(chunk_overlap if chunk_overlap is not None else settings.chunk_overlap, size // 2)
    chunks = _split_recursive(text, separators or SEPARATORS, size, overlap)
    logger.info("Recursive chunking produced %d chunks from %d chars", len(chunks), len(text))
    return chunks


# --------------------------------------------------------------------------
# semantic
# --------------------------------------------------------------------------


def split_sentences(text: str) -> list[str]:
    return [sentence.strip() for sentence in _SENTENCE_RE.split(text.strip()) if sentence.strip()]


def _context_windows(sentences: list[str], buffer_size: int) -> list[str]:
    """Pair each sentence with its neighbours so its embedding has context."""
    return [
        " ".join(sentences[max(0, i - buffer_size) : i + buffer_size + 1])
        for i in range(len(sentences))
    ]


def _embed(texts: list[str]) -> list[list[float]]:
    # Imported here so chunking stays importable without a configured Gemini client.
    from app.vectorstore import embed_texts

    embeddings = []
    for start in range(0, len(texts), EMBED_BATCH_SIZE):
        embeddings.extend(embed_texts(texts[start : start + EMBED_BATCH_SIZE], "RETRIEVAL_DOCUMENT"))
    return embeddings


def _cosine_distance(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    return 1.0 - (dot / norm) if norm else 1.0


def _percentile(values: list[float], percentile: float) -> float:
    """Linearly interpolated percentile (numpy's default method).

    Interpolating matters: a nearest-rank percentile always lands *on* an
    observed distance, so with few sentences the threshold equals the largest
    distance and `distance > threshold` never fires - no short document would
    ever be split.
    """
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = percentile / 100 * (len(ordered) - 1)
    lower = math.floor(position)
    upper = min(lower + 1, len(ordered) - 1)
    return ordered[lower] + (position - lower) * (ordered[upper] - ordered[lower])


def _group_sentences(sentences: list[str], distances: list[float]) -> list[str]:
    """Cut the sentence stream wherever a distance exceeds the threshold."""
    threshold = _percentile(distances, settings.chunk_breakpoint_percentile)
    groups, current = [], [sentences[0]]
    for i, distance in enumerate(distances):
        if distance > threshold:
            groups.append(" ".join(current))
            current = []
        current.append(sentences[i + 1])
    groups.append(" ".join(current))
    return groups


def _enforce_size(groups: list[str]) -> list[str]:
    """Split groups past the size cap, and merge ones too small to stand alone."""
    sized: list[str] = []
    for group in groups:
        if len(group) > settings.chunk_max_chars:
            # Never split into pieces larger than the cap we just exceeded.
            size = min(settings.chunk_size, settings.chunk_max_chars)
            sized.extend(recursive_chunk_text(group, size, settings.chunk_overlap))
        elif sized and len(group) < settings.chunk_min_chars:
            merged = f"{sized[-1]} {group}"
            if len(merged) <= settings.chunk_max_chars:
                sized[-1] = merged
            else:
                sized.append(group)
        else:
            sized.append(group)
    return sized


def semantic_chunk_text(text: str) -> list[str]:
    """Split text into topically coherent chunks."""
    text = text.strip()
    if not text:
        return []

    sentences = split_sentences(text)
    if len(sentences) < 2:
        return recursive_chunk_text(text)

    try:
        embeddings = _embed(_context_windows(sentences, settings.chunk_buffer_size))
        distances = [
            _cosine_distance(current, following)
            for current, following in zip(embeddings, embeddings[1:])
        ]
    except Exception:
        logger.exception("Semantic chunking failed; falling back to recursive chunks")
        return recursive_chunk_text(text)

    if not distances:
        return recursive_chunk_text(text)

    chunks = _enforce_size(_group_sentences(sentences, distances))
    logger.info("Semantic chunking produced %d chunks from %d sentences", len(chunks), len(sentences))
    return chunks


# --------------------------------------------------------------------------
# entry point
# --------------------------------------------------------------------------

STRATEGIES = {
    "recursive": recursive_chunk_text,
    "semantic": semantic_chunk_text,
    "character": chunk_text,
}


def chunk_document(text: str) -> list[str]:
    """Chunk `text` with the configured strategy."""
    strategy = STRATEGIES.get(settings.chunk_strategy)
    if strategy is None:
        logger.warning(
            "Unknown chunk_strategy %r; using recursive", settings.chunk_strategy
        )
        strategy = recursive_chunk_text
    return strategy(text)
