from pathlib import Path

from pypdf import PdfReader

from app.config import settings


def load_pdf(file_path: str) -> str:
    reader = PdfReader(file_path)
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def load_documents_dir(directory: str | None = None) -> list[dict]:
    docs_dir = Path(directory or settings.documents_dir)
    documents = []
    for pdf_path in sorted(docs_dir.glob("*.pdf")):
        documents.append({"source": pdf_path.name, "text": load_pdf(str(pdf_path))})
    return documents
