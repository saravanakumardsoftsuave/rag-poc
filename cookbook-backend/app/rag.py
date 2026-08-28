import uuid

from google import genai
from google.genai import types

from app.chunking import chunk_document
from app.config import settings
from app.keyword import index_chunks
from app.loader import load_documents_dir, load_file
from app.prompt import build_prompt
from app.retrieval import hybrid_search
from app.vectorstore import upsert_chunks

_client: genai.Client | None = None
NO_RELEVANT_ANSWER = (
    "I couldn't find that detail in the uploaded document. "
    "Please ask about information covered by your uploaded file."
)


def get_gemini_client() -> genai.Client:
    global _client
    if not settings.gemini_api_key:
        raise RuntimeError("GEMINI_API_KEY is not configured.")
    if _client is None:
        _client = genai.Client(api_key=settings.gemini_api_key)
    return _client


def generate_answer(prompt: str) -> str:
    response = get_gemini_client().models.generate_content(
        model=settings.gemini_generation_model,
        contents=prompt,
        config=types.GenerateContentConfig(max_output_tokens=4096),
    )
    return (response.text or "I couldn't generate an answer from the supplied cookbook context.").strip()


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
    matches = hybrid_search(question, k=k)
    relevant_matches = [match for match in matches]
    if not relevant_matches:
        return {"answer": NO_RELEVANT_ANSWER, "sources": []}
    prompt = build_prompt(question, [match["text"] for match in matches])
    answer = generate_answer(prompt)
    sources = sorted({match["source"] for match in relevant_matches})
    return {"answer": answer, "sources": sources}
