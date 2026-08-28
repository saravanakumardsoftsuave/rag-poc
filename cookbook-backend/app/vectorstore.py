import logging

# pyrefly: ignore [missing-import]
from pinecone import Pinecone, ServerlessSpec
from google import genai
from google.genai import types

from app.config import settings

logger = logging.getLogger(__name__)

_pinecone_client: Pinecone | None = None
_gemini_client: genai.Client | None = None


def get_pinecone_client() -> Pinecone:
    global _pinecone_client
    if _pinecone_client is None:
        _pinecone_client = Pinecone(api_key=settings.pinecone_api_key)
    return _pinecone_client


def get_gemini_client() -> genai.Client:
    global _gemini_client
    if not settings.gemini_api_key:
        raise RuntimeError("GEMINI_API_KEY is not configured.")
    if _gemini_client is None:
        _gemini_client = genai.Client(api_key=settings.gemini_api_key)
    return _gemini_client


def embed_texts(texts: list[str], task_type: str) -> list[list[float]]:
    response = get_gemini_client().models.embed_content(
        model=settings.gemini_embedding_model,
        contents=texts,
        config=types.EmbedContentConfig(
            task_type=task_type,
            output_dimensionality=settings.gemini_embedding_dimensions,
        ),
    )
    return [embedding.values for embedding in response.embeddings]


def ensure_index(dimension: int) -> None:
    pc = get_pinecone_client()
    existing = {index.name for index in pc.list_indexes()}
    if settings.pinecone_index_name in existing:
        index_dimension = pc.describe_index(settings.pinecone_index_name).dimension
        if index_dimension != dimension:
            raise RuntimeError(
                f"Pinecone index '{settings.pinecone_index_name}' has dimension {index_dimension}, "
                f"but Gemini returned {dimension}. Use a new index name and re-ingest the documents."
            )
        return
    pc.create_index(
        name=settings.pinecone_index_name,
        dimension=dimension,
        metric="cosine",
        spec=ServerlessSpec(cloud=settings.pinecone_cloud, region=settings.pinecone_region),
    )


def get_index():
    return get_pinecone_client().Index(settings.pinecone_index_name)


def upsert_chunks(chunks: list[dict]) -> None:
    embeddings = embed_texts([chunk["text"] for chunk in chunks], "RETRIEVAL_DOCUMENT")
    ensure_index(dimension=len(embeddings[0]))
    vectors = [
        {
            "id": chunk["id"],
            "values": embedding,
            "metadata": {"text": chunk["text"], "source": chunk["source"]},
        }
        for chunk, embedding in zip(chunks, embeddings)
    ]
    get_index().upsert(vectors=vectors)


def similarity_search(query: str, k: int = 10) -> list[dict]:
    query_embedding = embed_texts([query], "RETRIEVAL_QUERY")[0]
    result = get_index().query(vector=query_embedding, top_k=k, include_metadata=True)
    return [
        {
            "id": match["id"],
            "text": match["metadata"]["text"],
            "source": match["metadata"].get("source", "unknown"),
            "score": match["score"],
        }
        for match in result["matches"]
    ]


def delete_chunks_by_source(source: str) -> None:
    try:
        pc = get_pinecone_client()
        existing = {index.name for index in pc.list_indexes()}
        if settings.pinecone_index_name not in existing:
            return
        index = get_index()
        if source == "documents/":
            index.delete(delete_all=True)
        else:
            index.delete(filter={"source": source})
    except Exception:
        logger.exception("Pinecone vector deletion failed for source '%s'", source)

