"""End-to-end test: real chunking, real embeddings, real Pinecone (dense +
sparse), real hybrid search, real cross-encoder reranker, real local LLM
generation - graded by an LLM judge (the same local model, see
tests/llm_judge.py) instead of a brittle substring match. No external LLM API
is involved anywhere in this test.

Scope: this exercises app.rag.ingest_file / answer_question directly, not the
FastAPI HTTP routes. The routes additionally require a live Postgres
connection (app/database.py) to track uploaded-document metadata and chat
logs - that's bookkeeping around the RAG pipeline, not the RAG pipeline
itself, and pulling it in would make this test depend on infrastructure that
has nothing to do with retrieval/generation quality. If you also want HTTP
route coverage, that's a separate test using TestClient + a real Postgres
instance.

Not run by default (see pytest.ini) - `pytest -m e2e` opts in. Runs against
the real Pinecone credentials in .env, so it's routed at disposable,
uniquely-named indexes that are deleted at the end, never the user's real
`cookbook-rag` / `cookbook-rag-sparse` indexes.

Costs real time: creates two live Pinecone serverless indexes, and
downloads/runs the local Qwen2.5-1.5B-Instruct model on first call (used
twice - once to generate the answer, once to judge it).
"""

from pathlib import Path

import pytest

from app.config import settings

pytestmark = pytest.mark.e2e

SAMBAR_DOC = """Sambar

A South Indian lentil stew made with toor dal (pigeon peas), tempered with
mustard seeds, curry leaves, and dried red chilies, and simmered with
tamarind and mixed vegetables. Serves 4.
"""


@pytest.fixture
def isolated_pinecone_indexes(monkeypatch):
    """Point this test at disposable Pinecone indexes and delete them
    afterward, so it never reads or writes the user's real cookbook data."""
    monkeypatch.setattr(settings, "pinecone_index_name", "cookbook-rag-e2e-test")
    monkeypatch.setattr(settings, "pinecone_sparse_index_name", "cookbook-rag-e2e-test-sparse")

    yield

    from app.vectorstore import get_pinecone_client

    pc = get_pinecone_client()
    existing = {index.name for index in pc.list_indexes()}
    for name in (settings.pinecone_index_name, settings.pinecone_sparse_index_name):
        if name in existing:
            pc.delete_index(name)


def test_query_answers_sambar_lentil_question_e2e(isolated_pinecone_indexes, tmp_path):
    from app.rag import answer_question, ingest_file
    from tests.llm_judge import judge_answer

    doc_path: Path = tmp_path / "sambar.txt"
    doc_path.write_text(SAMBAR_DOC, encoding="utf-8")

    chunks_ingested = ingest_file(str(doc_path), "sambar.txt")
    assert chunks_ingested > 0

    question = "What lentil does Sambar use?"
    result = answer_question(question)

    passed, verdict = judge_answer(
        question=question,
        answer=result["answer"],
        expected_facts="Sambar's main lentil is toor dal (pigeon peas).",
    )
    # Printed unconditionally (not just on failure) so the judge's score is
    # visible on a passing run too - run with `pytest -s` to see it.
    print(f"\nRAG answer: {result['answer']}")
    print(f"Judge verdict: {verdict}")
    assert passed, f"LLM judge rejected the answer.\nVerdict: {verdict}\nAnswer: {result['answer']}"
