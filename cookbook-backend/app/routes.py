import logging
import shutil
from pathlib import Path
from tempfile import NamedTemporaryFile

from fastapi import APIRouter, HTTPException, Request, UploadFile
from pydantic import BaseModel
from sqlmodel import select

from app.agent.core.budgets import Budgets
from app.agent.core.loop import run_agentic_loop
from app.database import ChatLog, DocumentRecord, SessionDep
from app.keyword import delete_chunks_by_source as delete_keyword_chunks
from app.loader import SUPPORTED_EXTENSIONS, UnsupportedDocumentError
from app.rag import ingest_directory, ingest_file
from app.vectorstore import delete_chunks_by_source

router = APIRouter(tags=["rag"])
logger = logging.getLogger(__name__)

DEFAULT_BUDGETS = Budgets(max_iterations=6, max_tokens=6000, max_cost_usd=0.05, timeout_s=90.0)


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
async def query(request: Request, body: QuestionRequest, session: SessionDep) -> QuestionResponse:
    try:
        loop_result = await run_agentic_loop(body.question, request.app.state.tool_registry, DEFAULT_BUDGETS)
    except Exception:
        logger.exception("Cookbook query failed")
        raise HTTPException(
            status_code=503,
            detail="The cookbook search service is temporarily unavailable. Please try again shortly.",
        ) from None

    if loop_result["status"] == "ok":
        answer, sources = loop_result["answer"], loop_result["sources"]
    elif loop_result["status"] == "budget_exceeded":
        logger.warning("query hit budget %s for question=%r", loop_result["budget"], body.question)
        answer, sources = "That request needed more steps than I'm allowed to take. Please try rephrasing it.", []
    else:
        logger.warning("query failed (%s) for question=%r", loop_result.get("reason"), body.question)
        answer, sources = "I wasn't able to work out an answer to that. Please try rephrasing it.", []

    session.add(ChatLog(question=body.question, answer=answer, source_documents=",".join(sources)))
    session.commit()
    return QuestionResponse(answer=answer, sources=sources)


@router.post("/ingest")
def ingest(session: SessionDep) -> IngestResponse:
    chunk_count = ingest_directory()
    session.add(DocumentRecord(filename="documents/", chunk_count=chunk_count))
    session.commit()
    return IngestResponse(chunks_ingested=chunk_count)


@router.post("/upload")
async def upload(file: UploadFile, session: SessionDep) -> UploadResponse:
    filename = file.filename or "uploaded.txt"
    with NamedTemporaryFile(suffix=Path(filename).suffix, delete=False) as tmp:
        shutil.copyfileobj(file.file, tmp)
        tmp_path = tmp.name
    try:
        if Path(tmp_path).stat().st_size == 0:
            raise HTTPException(
                status_code=422,
                detail="The uploaded file is empty. Please choose a valid document and try again.",
            )
        chunk_count = ingest_file(tmp_path, filename)
        if chunk_count == 0:
            raise HTTPException(
                status_code=422,
                detail="No readable text was found in this document. Scanned images are not supported.",
            )
    except HTTPException:
        raise
    except UnsupportedDocumentError as exc:
        raise HTTPException(status_code=415, detail=str(exc)) from None
    except Exception:
        logger.exception("Document upload failed for %s", filename)
        raise HTTPException(
            status_code=503,
            detail="The document could not be indexed right now. Please try again shortly.",
        ) from None
    finally:
        Path(tmp_path).unlink(missing_ok=True)
    session.add(DocumentRecord(filename=filename, chunk_count=chunk_count))
    session.commit()
    return UploadResponse(filename=filename, chunks_ingested=chunk_count)


@router.get("/supported-formats")
def supported_formats() -> dict[str, list[str]]:
    return {"extensions": SUPPORTED_EXTENSIONS}


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
    delete_keyword_chunks(record.filename)
    session.delete(record)
    session.commit()
    return DeleteDocumentResponse(message="Document deleted successfully.", id=document_id)


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}

