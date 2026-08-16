import logging
import shutil
from pathlib import Path
from tempfile import NamedTemporaryFile

from fastapi import APIRouter, HTTPException, UploadFile
from pydantic import BaseModel
from sqlmodel import select

from app.database import ChatLog, DocumentRecord, SessionDep
from app.rag import NO_RELEVANT_ANSWER, answer_question, ingest_directory, ingest_pdf
from app.vectorstore import delete_chunks_by_source

router = APIRouter(tags=["rag"])
logger = logging.getLogger(__name__)


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


class DocumentResponse(BaseModel):
    id: int
    filename: str
    chunks_ingested: int
    created_at: str


class DeleteDocumentResponse(BaseModel):
    message: str
    id: int


@router.post("/query")
def query(request: QuestionRequest, session: SessionDep) -> QuestionResponse:
    has_documents = session.exec(select(DocumentRecord.id).limit(1)).first() is not None
    if not has_documents:
        return QuestionResponse(answer=NO_RELEVANT_ANSWER, sources=[])

    try:
        result = answer_question(request.question)
    except Exception:
        logger.exception("Cookbook query failed")
        raise HTTPException(
            status_code=503,
            detail="The cookbook search service is temporarily unavailable. Please try again shortly.",
        ) from None
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
        if Path(tmp_path).stat().st_size == 0:
            raise HTTPException(
                status_code=422,
                detail="The uploaded PDF is empty. Please choose a valid cookbook PDF and try again.",
            )
        chunk_count = ingest_pdf(tmp_path, filename)
    except HTTPException:
        raise
    except Exception:
        logger.exception("Cookbook upload failed for %s", filename)
        raise HTTPException(
            status_code=503,
            detail="The cookbook could not be indexed right now. Please try again shortly.",
        ) from None
    finally:
        Path(tmp_path).unlink(missing_ok=True)
    session.add(DocumentRecord(filename=filename, chunk_count=chunk_count))
    session.commit()
    return UploadResponse(filename=filename, chunks_ingested=chunk_count)


@router.get("/documents", response_model=list[DocumentResponse])
def list_documents(session: SessionDep) -> list[DocumentResponse]:
    records = session.exec(
        select(DocumentRecord).order_by(DocumentRecord.created_at.desc())
    ).all()
    return [
        DocumentResponse(
            id=record.id,
            filename=record.filename,
            chunks_ingested=record.chunk_count,
            created_at=record.created_at.isoformat(),
        )
        for record in records
        if record.id is not None
    ]


@router.delete("/documents/{document_id}", response_model=DeleteDocumentResponse)
def delete_document(document_id: int, session: SessionDep) -> DeleteDocumentResponse:
    record = session.get(DocumentRecord, document_id)
    if not record:
        raise HTTPException(status_code=404, detail="Document not found.")

    delete_chunks_by_source(record.filename)
    session.delete(record)
    session.commit()
    return DeleteDocumentResponse(message="Document deleted successfully.", id=document_id)


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}

