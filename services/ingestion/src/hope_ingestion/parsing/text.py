"""Native, visibility-aware text extraction for PDF, DOCX, HTML and plain text."""

from __future__ import annotations

import io
import json
import re
from dataclasses import dataclass, field
from typing import Any

from bs4 import BeautifulSoup, Tag
from hope_core.schemas.grant_opportunity import PipelinePath

from hope_ingestion.artifacts import DOCX, HTML, JSON, PDF, TEXT, XML

MIN_CHARS_PER_PAGE = 40
MIN_LETTER_RATIO = 0.5
HIDDEN_STYLE = re.compile(r"display\s*:\s*none|visibility\s*:\s*hidden|font-size\s*:\s*0", re.I)
WHITE = {(1.0,), (1.0, 1.0, 1.0), (0.0, 0.0, 0.0, 0.0)}


class CorruptDocumentError(ValueError):
    pass


@dataclass(frozen=True)
class Page:
    number: int
    text: str


@dataclass
class DocumentText:
    artifact_id: str
    media_type: str
    pages: list[Page]
    hidden_text: list[str] = field(default_factory=list)
    pipeline_path: list[PipelinePath] = field(default_factory=lambda: ["native_text"])

    @property
    def text(self) -> str:
        return "\n".join(page.text for page in self.pages)


def text_quality_ok(doc: DocumentText) -> bool:
    """False for scans and garbled text, which go to the OCR fallback."""
    text = doc.text
    if not doc.pages or len(text.strip()) < MIN_CHARS_PER_PAGE * len(doc.pages) / 4:
        return False
    visible = [c for c in text if not c.isspace()]
    letters = sum(c.isalnum() for c in visible)
    return bool(visible) and letters / len(visible) >= MIN_LETTER_RATIO


def _pdf_char_hidden(obj: dict[str, Any]) -> bool:
    color = obj.get("non_stroking_color")
    rgb = tuple(float(c) for c in color) if isinstance(color, list | tuple) else None
    return float(obj.get("size") or 10) < 1 or rgb in WHITE


def _pdf(data: bytes) -> tuple[list[Page], list[str]]:
    import pdfplumber

    pages: list[Page] = []
    hidden: list[str] = []
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        for number, page in enumerate(pdf.pages, start=1):
            chars = page.chars
            secret = "".join(c["text"] for c in chars if _pdf_char_hidden(c)).strip()
            if secret:
                hidden.append(secret)
            visible = page.filter(
                lambda obj: obj.get("object_type") != "char" or not _pdf_char_hidden(obj)
            )
            pages.append(Page(number, visible.extract_text() or ""))
    return pages, hidden


def _docx(data: bytes) -> tuple[list[Page], list[str]]:
    import docx

    document = docx.Document(io.BytesIO(data))
    lines: list[str] = []
    hidden: list[str] = []
    for paragraph in document.paragraphs:
        shown = []
        for run in paragraph.runs:
            color = run.font.color.rgb if run.font.color and run.font.color.type else None
            if run.font.hidden or str(color) == "FFFFFF":
                hidden.append(run.text)
            else:
                shown.append(run.text)
        lines.append("".join(shown))
    for table in document.tables:
        for row in table.rows:
            lines.append(" | ".join(cell.text for cell in row.cells))
    return [Page(1, "\n".join(lines))], [h for h in hidden if h.strip()]


def _html(data: bytes) -> tuple[list[Page], list[str]]:
    soup = BeautifulSoup(data, "html.parser")
    for tag in soup(["script", "style", "noscript", "template", "iframe", "object", "embed"]):
        tag.decompose()
    hidden: list[str] = []
    for tag in soup.find_all(True):
        if not isinstance(tag, Tag) or tag.decomposed:
            continue
        if tag.has_attr("hidden") or HIDDEN_STYLE.search(str(tag.get("style") or "")):
            hidden.append(tag.get_text(" ", strip=True))
            tag.decompose()
    text = re.sub(r"\n\s*\n+", "\n", soup.get_text("\n"))
    return [Page(1, text.strip())], [h for h in hidden if h]


def extract_text(data: bytes, media_type: str, artifact_id: str) -> DocumentText:
    try:
        if media_type == PDF:
            pages, hidden = _pdf(data)
        elif media_type == DOCX:
            pages, hidden = _docx(data)
        elif media_type == HTML:
            pages, hidden = _html(data)
        elif media_type == JSON:
            pages, hidden = [Page(1, json.dumps(json.loads(data), indent=1))], []
        elif media_type in (TEXT, XML):
            pages, hidden = [Page(1, data.decode("utf-8"))], []
        else:
            raise CorruptDocumentError(f"unsupported media type {media_type}")
    except CorruptDocumentError:
        raise
    except Exception as exc:
        raise CorruptDocumentError(f"{media_type}: {type(exc).__name__}: {exc}") from exc
    if not pages:
        raise CorruptDocumentError(f"{media_type}: no pages")
    return DocumentText(artifact_id, media_type, pages, hidden)
