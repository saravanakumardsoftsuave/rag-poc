import shutil
from pathlib import Path
from tempfile import NamedTemporaryFile

from fastapi import APIRouter, UploadFile
from pydantic import BaseModel

from app.database import ChatLog, DocumentRecord, SessionDep
from app.rag import answer_question, ingest_directory, ingest_pdf

router = APIRouter(tags=["rag"])


class QuestionRequest(BaseModel):
    question: str


class QuestionResponse(BaseModel):
    answer: str
    sources: list[str]


class IngestResponse(BaseModel):
    chunks_ingested: int


class UploadResponse(BaseModel):
    filename: str
    chunks_ingested: int


@router.post("/query")
def query(request: QuestionRequest, session: SessionDep) -> QuestionResponse:
    result = answer_question(request.question)
    session.add(
        ChatLog(
            question=request.question,
            answer=result["answer"],
            source_documents=",".join(result["sources"]),
        )
    )
    session.commit()
    return QuestionResponse(**result)


@router.post("/ingest")
def ingest(session: SessionDep) -> IngestResponse:
    chunk_count = ingest_directory()
    session.add(DocumentRecord(filename="documents/", chunk_count=chunk_count))
    session.commit()
    return IngestResponse(chunks_ingested=chunk_count)


@router.post("/upload")
async def upload(file: UploadFile, session: SessionDep) -> UploadResponse:
    with NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        shutil.copyfileobj(file.file, tmp)
        tmp_path = tmp.name
    filename = file.filename or "uploaded.pdf"
    try:
        chunk_count = ingest_pdf(tmp_path, filename)
    finally:
        Path(tmp_path).unlink(missing_ok=True)
    session.add(DocumentRecord(filename=filename, chunk_count=chunk_count))
    session.commit()
    return UploadResponse(filename=filename, chunks_ingested=chunk_count)


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
