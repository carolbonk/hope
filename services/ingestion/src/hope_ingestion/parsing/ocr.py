"""OCR / vision fallback for scanned or garbled documents (blueprint 8.5).

STUB: Phase 1 ships no OCR engine. `NoOcr` always returns None, so the pipeline marks the
document unreadable and routes it to NeedsParseReview. A Textract/Docling/vision-LLM engine
implements `OcrEngine` later without pipeline changes.
"""

from __future__ import annotations

from typing import Protocol

from hope_ingestion.parsing.text import DocumentText


class OcrEngine(Protocol):
    name: str

    def recognize(self, data: bytes, doc: DocumentText) -> DocumentText | None: ...


class NoOcr:
    name = "ocr-stub"

    def recognize(self, data: bytes, doc: DocumentText) -> DocumentText | None:
        return None
