"""Hybrid retrieval: Pinecone dense (semantic) + Pinecone sparse BM25 (keyword),
fused with RRF, then reranked with a cross-encoder so lexically-specific chunks
that lose on RRF rank alone still get a fair shot at the final top-k."""

from sentence_transformers import CrossEncoder

from app.config import settings
from app.keyword import keyword_search
from app.vectorstore import similarity_search

_reranker: CrossEncoder | None = None


def _get_reranker() -> CrossEncoder:
    global _reranker
    if _reranker is None:
        _reranker = CrossEncoder(settings.reranker_model)
    return _reranker


def _fuse(ranked_lists: list[list[dict]], rrf_k: int) -> list[dict]:
    """Reciprocal Rank Fusion: score a chunk by 1/(rrf_k + rank) summed across lists."""
    fused: dict[str, dict] = {}
    for matches in ranked_lists:
        for rank, match in enumerate(matches, start=1):
            key = match.get("id") or f"{match['source']}::{match['text']}"
            entry = fused.setdefault(
                key,
                {
                    "id": match.get("id"),
                    "text": match["text"],
                    "source": match["source"],
                    "rrf_score": 0.0,
                },
            )
            entry["rrf_score"] += 1.0 / (rrf_k + rank)
    return sorted(fused.values(), key=lambda match: match["rrf_score"], reverse=True)


def _rerank(query: str, candidates: list[dict]) -> list[dict]:
    if not candidates:
        return candidates
    pairs = [(query, candidate["text"]) for candidate in candidates]
    scores = _get_reranker().predict(pairs)
    for candidate, score in zip(candidates, scores):
        candidate["rerank_score"] = float(score)
    return sorted(candidates, key=lambda match: match["rerank_score"], reverse=True)


def hybrid_search(query: str, k: int | None = None) -> tuple[list[dict], float]:
    """Returns (top-k reranked chunks, best raw semantic similarity score).

    The semantic score is the raw Pinecone cosine similarity of the single best
    dense match, captured before RRF fusion collapses everything to a rank-based
    score - fusion can't distinguish "no good match" from "best of a bad lot"
    since a chunk still ranks #1 in a returned list even when nothing in the
    corpus is actually relevant. `answer_question` uses this raw score to decide
    whether to answer at all.
    """
    semantic = similarity_search(query, k=settings.semantic_top_k)
    keyword = keyword_search(query, k=settings.keyword_top_k)
    best_semantic_score = semantic[0]["score"] if semantic else 0.0

    candidates = _fuse([semantic, keyword], settings.rrf_k)[: settings.rerank_candidate_pool]
    reranked = _rerank(query, candidates)[: k or settings.hybrid_top_k]
    return reranked, best_semantic_score
