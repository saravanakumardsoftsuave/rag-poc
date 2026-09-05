import logging
import uuid

from transformers import pipeline

from app.chunking import chunk_document
from app.config import settings
from app.keyword import index_chunks
from app.loader import load_documents_dir, load_file
from app.prompt import build_prompt
from app.retrieval import hybrid_search
from app.vectorstore import upsert_chunks

logger = logging.getLogger(__name__)

_generator = None
NO_RELEVANT_ANSWER = (
    "I couldn't find that detail in the uploaded document. "
    "Please ask about information covered by your uploaded file."
)
FALLBACK_ANSWER = "I couldn't generate an answer from the supplied cookbook context."


def get_generator():
    global _generator
    if _generator is None:
        _generator = pipeline("text-generation", model=settings.hf_generation_model)
    return _generator


def count_tokens(text: str) -> int:
    """Token count via the generation model's own tokenizer - used for the
    agent/workflow's token budget and benchmark reporting, not billing (this
    model runs locally; there's no per-token cost to meter)."""
    return len(get_generator().tokenizer(text)["input_ids"])


def generate_answer(prompt: str) -> str:
    output = get_generator()(
        [{"role": "user", "content": prompt}],
        max_new_tokens=settings.hf_generation_max_new_tokens,
        do_sample=False,
    )
    reply = output[0]["generated_text"][-1]["content"]
    return reply.strip() or FALLBACK_ANSWER


def _ingest(source: str, text: str) -> int:
    chunks = chunk_document(text)
    if not chunks:
        return 0
    records = [
        {"id": f"{source}#{i}-{uuid.uuid4().hex[:8]}", "text": chunk, "source": source}
        for i, chunk in enumerate(chunks)
    ]
    upsert_chunks(records)
    index_chunks(records)
    return len(chunks)


def ingest_directory(directory: str | None = None) -> int:
    total = 0
    for doc in load_documents_dir(directory):
        total += _ingest(doc["source"], doc["text"])
    return total


def ingest_file(file_path: str, source_name: str) -> int:
    return _ingest(source_name, load_file(file_path, source_name))


def answer_question(question: str, k: int | None = None) -> dict:
    matches, best_semantic_score = hybrid_search(question, k=k)
    logger.info(
        "query=%r best_semantic_score=%.4f retrieved=%s",
        question,
        best_semantic_score,
        [
            {
                "id": match.get("id"),
                "source": match["source"],
                "rrf_score": round(match.get("rrf_score", 0.0), 4),
                "rerank_score": round(match.get("rerank_score", 0.0), 4),
            }
            for match in matches
        ],
    )
    if not matches or best_semantic_score < settings.relevance_score_cutoff:
        return {"answer": NO_RELEVANT_ANSWER, "sources": []}
    prompt = build_prompt(question, [match["text"] for match in matches])
    answer = generate_answer(prompt)
    sources = sorted({match["source"] for match in matches})
    return {"answer": answer, "sources": sources}
