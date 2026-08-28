"""Keyword retrieval backed by Pinecone's built-in sparse (BM25) index.

Chunks are upserted as *records* into a sparse index created with integrated
inference (`pinecone-sparse-english-v0`), so Pinecone does the tokenizing,
stemming and lexical scoring server-side. Nothing is indexed in-process and no
chunk mirror is kept in Postgres.
"""

import logging

from app.config import settings
from app.vectorstore import get_pinecone_client

logger = logging.getLogger(__name__)

# Field that holds the chunk body. It is mapped to the sparse model's "text"
# input, so Pinecone embeds it on write and on query.
TEXT_FIELD = "chunk_text"

# Pinecone embeds records server-side; keep batches within its per-request limit.
UPSERT_BATCH_SIZE = 96


def get_sparse_index():
    return get_pinecone_client().Index(settings.pinecone_sparse_index_name)


def _sparse_index_exists() -> bool:
    pc = get_pinecone_client()
    return settings.pinecone_sparse_index_name in {index.name for index in pc.list_indexes()}


def ensure_sparse_index() -> None:
    """Create the sparse index on first use, with the BM25 model attached."""
    if _sparse_index_exists():
        return
    get_pinecone_client().create_index_for_model(
        name=settings.pinecone_sparse_index_name,
        cloud=settings.pinecone_cloud,
        region=settings.pinecone_region,
        embed={
            "model": settings.pinecone_sparse_model,
            "field_map": {"text": TEXT_FIELD},
        },
    )
    logger.info("Created Pinecone sparse index '%s'", settings.pinecone_sparse_index_name)


def index_chunks(chunks: list[dict]) -> None:
    """Upsert chunks so they are reachable by keyword search."""
    if not chunks:
        return
    ensure_sparse_index()
    records = [
        {"_id": chunk["id"], TEXT_FIELD: chunk["text"], "source": chunk["source"]}
        for chunk in chunks
    ]
    index = get_sparse_index()
    for start in range(0, len(records), UPSERT_BATCH_SIZE):
        index.upsert_records(
            namespace=settings.pinecone_namespace,
            records=records[start : start + UPSERT_BATCH_SIZE],
        )


def keyword_search(query: str, k: int = 10) -> list[dict]:
    """Sparse (BM25) search over chunk text. Degrades to no results on failure."""
    if not query.strip():
        return []
    try:
        response = get_sparse_index().search(
            namespace=settings.pinecone_namespace,
            query={"inputs": {"text": query}, "top_k": k},
            fields=[TEXT_FIELD, "source"],
        )
    except Exception:
        logger.exception("Pinecone sparse search failed for query '%s'", query)
        return []

    matches = []
    for hit in response.result.hits:
        fields = hit.fields or {}
        matches.append(
            {
                "id": hit.id,
                "text": fields.get(TEXT_FIELD, ""),
                "source": fields.get("source", "unknown"),
                "score": hit.score,
            }
        )
    return matches


def delete_chunks_by_source(source: str) -> None:
    """Remove a document's chunks. Serverless indexes cannot delete by metadata
    filter, so chunks are found by their `"{source}#..."` id prefix."""
    try:
        if not _sparse_index_exists():
            return
        index = get_sparse_index()
        namespace = settings.pinecone_namespace
        if source == "documents/":
            index.delete(delete_all=True, namespace=namespace)
            return
        for page in index.list(prefix=f"{source}#", namespace=namespace):
            ids = [item.id for item in page.vectors]
            if ids:
                index.delete(ids=ids, namespace=namespace)
    except Exception:
        logger.exception("Sparse chunk deletion failed for source '%s'", source)
