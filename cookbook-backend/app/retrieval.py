"""Hybrid retrieval: Pinecone dense (semantic) + Pinecone sparse BM25 (keyword), fused with RRF."""

from app.config import settings
from app.keyword import keyword_search
from app.vectorstore import similarity_search


def _fuse(ranked_lists: list[list[dict]], rrf_k: int) -> list[dict]:
    """Reciprocal Rank Fusion: score a chunk by 1/(rrf_k + rank) summed across lists."""
    fused: dict[str, dict] = {}
    for matches in ranked_lists:
        for rank, match in enumerate(matches, start=1):
            key = match.get("id") or f"{match['source']}::{match['text']}"
            entry = fused.setdefault(
                key,
                {"text": match["text"], "source": match["source"], "score": 0.0},
            )
            entry["score"] += 1.0 / (rrf_k + rank)
    return sorted(fused.values(), key=lambda match: match["score"], reverse=True)


def hybrid_search(query: str, k: int | None = None) -> list[dict]:
    semantic = similarity_search(query, k=settings.semantic_top_k)
    keyword = keyword_search(query, k=settings.keyword_top_k)
    return _fuse([semantic, keyword], settings.rrf_k)[: k or settings.hybrid_top_k]
