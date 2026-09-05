"""Text transcription for files that carry no extractable text of their own.

Scans, photographs and image-only PDFs are handed to Gemini, which reads both
images and PDFs natively - so a scanned cookbook page becomes text without
Tesseract, Poppler, or any other binary on the host.
"""

import logging

from google.genai import types

from app.config import settings
from app.vectorstore import get_gemini_client

logger = logging.getLogger(__name__)

IMAGE_MIME_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".gif": "image/gif",
    ".bmp": "image/bmp",
    ".tif": "image/tiff",
    ".tiff": "image/tiff",
    ".heic": "image/heic",
    ".heif": "image/heif",
}

PROMPT = (
    "Transcribe every piece of text in this document, in reading order. "
    "Keep headings, lists and table rows on their own lines; render a table row "
    "as cells separated by ' | '. Reproduce the text verbatim - do not "
    "summarise, translate, describe images, or add commentary of your own. "
    "If the document contains no legible text at all, reply with nothing."
)


def transcribe(data: bytes, mime_type: str) -> str:
    """Return the text Gemini reads out of an image or PDF. '' if there is none."""
    if not settings.ocr_enabled:
        return ""
    if len(data) > settings.ocr_max_bytes:
        raise ValueError(
            f"The file is too large to transcribe ({len(data) / 1_000_000:.1f} MB; "
            f"the limit is {settings.ocr_max_bytes / 1_000_000:.1f} MB)."
        )
    response = get_gemini_client().models.generate_content(
        model=settings.ocr_model or settings.gemini_generation_model,
        contents=[
            types.Part.from_bytes(data=data, mime_type=mime_type),
            PROMPT,
        ],
        config=types.GenerateContentConfig(
            max_output_tokens=settings.ocr_max_output_tokens,
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        ),
    )
    text = (response.text or "").strip()
    logger.info("Transcribed %s (%d bytes) into %d chars", mime_type, len(data), len(text))
    return text
