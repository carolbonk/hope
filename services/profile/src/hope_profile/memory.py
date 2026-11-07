"""Semantic memory: narrative assets chunked into pgvector, searched by cosine similarity."""

from __future__ import annotations

import re
from typing import Literal
from uuid import UUID

from hope_core.db import tenant_tx
from hope_core.hashing import content_hash
from hope_core.model_gateway import ModelGateway
from hope_core.schemas.common import Provenance
from psycopg.types.json import Jsonb

from hope_profile.contracts import NarrativeHit
from hope_profile.repository import Conn

AssetKind = Literal["boilerplate", "outcome", "bio", "program", "mission", "other"]
MAX_CHUNK_CHARS = 1200
_SENTENCE = re.compile(r"(?<=[.!?])\s+")


def _pieces(paragraph: str, max_chars: int) -> list[str]:
    if len(paragraph) <= max_chars:
        return [paragraph]
    pieces: list[str] = []
    for sentence in _SENTENCE.split(paragraph):
        pieces.extend(sentence[i : i + max_chars] for i in range(0, len(sentence), max_chars))
    return pieces


def chunk_text(text: str, max_chars: int = MAX_CHUNK_CHARS) -> list[str]:
    """Pack paragraphs (then sentences) into chunks of at most `max_chars`."""
    chunks: list[str] = []
    current = ""
    for paragraph in (p.strip() for p in re.split(r"\n\s*\n", text)):
        for piece in _pieces(paragraph, max_chars) if paragraph else []:
            if current and len(current) + 1 + len(piece) > max_chars:
                chunks.append(current)
                current = ""
            current = f"{current}\n{piece}" if current else piece
    return [*chunks, current] if current else chunks


def _vector(values: list[float]) -> str:
    return "[" + ",".join(f"{v:.7g}" for v in values) + "]"


class NarrativeMemory:
    def __init__(self, conn: Conn, gateway: ModelGateway) -> None:
        self.conn = conn
        self.gateway = gateway

    def index_asset(
        self,
        tenant_id: UUID,
        agency_id: UUID,
        asset_id: str,
        kind: AssetKind,
        text: str,
        *,
        approved_for_reuse: bool = False,
        provenance: Provenance | None = None,
    ) -> int:
        """(Re)index one asset, replacing its previous chunks. Returns the chunk count."""
        chunks = chunk_text(text)
        vectors = self.gateway.embed(chunks) if chunks else []
        prov = Jsonb(provenance.model_dump(mode="json")) if provenance else None
        with tenant_tx(self.conn, tenant_id) as cur:
            cur.execute(
                "DELETE FROM narrative_chunks WHERE agency_id = %s AND asset_id = %s",
                (agency_id, asset_id),
            )
            for index, (chunk, vector) in enumerate(zip(chunks, vectors, strict=True)):
                cur.execute(
                    "INSERT INTO narrative_chunks (tenant_id, agency_id, asset_id, asset_kind,"
                    " chunk_index, content, content_hash, embedding, approved_for_reuse,"
                    " provenance) VALUES (%s, %s, %s, %s, %s, %s, %s, %s::vector, %s, %s)",
                    (
                        tenant_id,
                        agency_id,
                        asset_id,
                        kind,
                        index,
                        chunk,
                        content_hash({"content": chunk}),
                        _vector(vector),
                        approved_for_reuse,
                        prov,
                    ),
                )
        return len(chunks)

    def set_approved_for_reuse(
        self, tenant_id: UUID, agency_id: UUID, asset_id: str, approved: bool
    ) -> int:
        with tenant_tx(self.conn, tenant_id) as cur:
            cur.execute(
                "UPDATE narrative_chunks SET approved_for_reuse = %s"
                " WHERE agency_id = %s AND asset_id = %s",
                (approved, agency_id, asset_id),
            )
            return cur.rowcount

    def search(
        self,
        tenant_id: UUID,
        query: str,
        k: int = 5,
        *,
        agency_id: UUID | None = None,
        approved_only: bool = True,
    ) -> list[NarrativeHit]:
        [vector] = self.gateway.embed([query])
        with tenant_tx(self.conn, tenant_id) as cur:
            cur.execute(
                "SELECT chunk_id, agency_id, asset_id, asset_kind, chunk_index, content,"
                " approved_for_reuse, provenance, 1 - (embedding <=> %(q)s::vector) AS score"
                " FROM narrative_chunks"
                " WHERE vector_dims(embedding) = %(dims)s"
                " AND (%(agency)s::uuid IS NULL OR agency_id = %(agency)s)"
                " AND (approved_for_reuse OR NOT %(approved_only)s)"
                " ORDER BY embedding <=> %(q)s::vector LIMIT %(k)s",
                {
                    "q": _vector(vector),
                    "dims": len(vector),
                    "agency": agency_id,
                    "approved_only": approved_only,
                    "k": k,
                },
            )
            return [NarrativeHit.model_validate(row) for row in cur.fetchall()]
