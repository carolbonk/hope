"""Split page text into sections for section-wise extraction. Sections never span pages,
so every quote maps back to one page for its Evidence."""

from __future__ import annotations

import itertools
import re
from dataclasses import dataclass

from hope_ingestion.parsing.text import DocumentText

HEADING = re.compile(
    r"^(?:(?:section|part|article)\s+)?(?:[IVX]+|\d+(?:\.\d+)*|[A-Z])[.)]\s+\S.{0,80}$"
    r"|^[A-Z][A-Z0-9 ,&/()'-]{3,80}:?$",
)
MAX_SECTION_CHARS = 6000


@dataclass(frozen=True)
class Section:
    section_id: str
    title: str
    artifact_id: str
    page: int
    offset: int
    text: str


def split_sections(doc: DocumentText, max_chars: int = MAX_SECTION_CHARS) -> list[Section]:
    sections: list[Section] = []
    for page in doc.pages:
        starts = [0]
        for match in re.finditer(r"^.*$", page.text, re.M):
            if match.start() and HEADING.match(match.group().strip()):
                starts.append(match.start())
        starts.append(len(page.text))
        for begin, end in itertools.pairwise(starts):
            for chunk in range(begin, end, max_chars):
                body = page.text[chunk : min(end, chunk + max_chars)]
                if not body.strip():
                    continue
                title = body.strip().splitlines()[0][:120]
                sections.append(
                    Section(
                        section_id=f"{doc.artifact_id}:p{page.number}:{len(sections) + 1}",
                        title=title,
                        artifact_id=doc.artifact_id,
                        page=page.number,
                        offset=chunk,
                        text=body,
                    )
                )
    return sections
