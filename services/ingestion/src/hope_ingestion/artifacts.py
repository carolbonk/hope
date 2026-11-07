"""Immutable, content-addressed raw artifacts on S3/MinIO with rows in `artifacts`
(blueprint 2.2 A1, 8.3, 8.5). Disallowed or active content is quarantined, never stored."""

from __future__ import annotations

import hashlib
import io
import re
import zipfile
from dataclasses import dataclass, field
from typing import Any, Protocol
from uuid import UUID

from hope_core.envelope import DataClassification
from hope_core.settings import get_settings

PDF = "application/pdf"
DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
HTML = "text/html"
XML = "application/xml"
JSON = "application/json"
TEXT = "text/plain"
ALLOWED_MEDIA_TYPES = frozenset({PDF, DOCX, HTML, XML, JSON, TEXT})

PDF_ACTIVE = re.compile(rb"/(JavaScript|JS|Launch|EmbeddedFile|RichMedia|SubmitForm|ImportData)\b")
PDF_ENCRYPTED = re.compile(rb"/Encrypt\b")
DOCX_ACTIVE_PARTS = ("vbaProject.bin", "activeX/", "vbaData.xml", "embeddings/")


class ArtifactRejectedError(ValueError):
    def __init__(self, reason: str, sha256: str) -> None:
        super().__init__(reason)
        self.reason = reason
        self.sha256 = sha256


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sniff_media_type(data: bytes) -> str | None:
    """Trust magic bytes, not file names or Content-Type headers."""
    head = data[:1024].lstrip()
    if data.startswith(b"%PDF-"):
        return PDF
    if data.startswith(b"PK\x03\x04"):
        try:
            names = zipfile.ZipFile(io.BytesIO(data)).namelist()
        except zipfile.BadZipFile:
            return None
        return DOCX if "word/document.xml" in names else None
    lowered = head.lower()
    if lowered.startswith((b"<!doctype html", b"<html")) or b"<body" in lowered:
        return HTML
    if lowered.startswith(b"<?xml"):
        return XML
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return None
    if "\x00" in text:
        return None
    return JSON if text.lstrip().startswith(("{", "[")) else TEXT


def active_content_reason(data: bytes, media_type: str) -> str | None:
    if media_type == PDF:
        if PDF_ENCRYPTED.search(data):
            return "pdf_encrypted"
        match = PDF_ACTIVE.search(data)
        return f"pdf_active_content:{match.group(1).decode()}" if match else None
    if media_type == DOCX:
        archive = zipfile.ZipFile(io.BytesIO(data))
        for name in archive.namelist():
            if any(part in name for part in DOCX_ACTIVE_PARTS):
                return f"docx_active_content:{name}"
        content_types = archive.read("[Content_Types].xml").decode("utf-8", "replace")
        if "macroEnabled" in content_types:
            return "docx_macro_enabled"
    return None


@dataclass(frozen=True)
class StoredArtifact:
    artifact_id: str
    sha256: str
    storage_uri: str
    media_type: str
    size: int
    filename: str | None = None


class BlobStore(Protocol):
    def put(self, key: str, data: bytes, content_type: str) -> str: ...

    def get(self, key: str) -> bytes: ...


@dataclass
class InMemoryBlobStore:
    bucket: str = "hope-artifacts"
    blobs: dict[str, bytes] = field(default_factory=dict)

    def put(self, key: str, data: bytes, content_type: str) -> str:
        self.blobs.setdefault(key, data)
        return f"s3://{self.bucket}/{key}"

    def get(self, key: str) -> bytes:
        return self.blobs[key]


class S3BlobStore:
    """S3 or MinIO (HOPE_S3_*). Objects are written once; the key is the content hash."""

    def __init__(self, client: Any | None = None, bucket: str | None = None) -> None:
        settings = get_settings()
        if client is None:
            import boto3

            client = boto3.client(
                "s3",
                endpoint_url=settings.s3_endpoint,
                aws_access_key_id=settings.s3_access_key,
                aws_secret_access_key=settings.s3_secret_key,
            )
        self.client = client
        self.bucket = bucket or settings.s3_bucket

    def put(self, key: str, data: bytes, content_type: str) -> str:
        self.client.put_object(
            Bucket=self.bucket,
            Key=key,
            Body=data,
            ContentType=content_type,
            ChecksumAlgorithm="SHA256",
        )
        return f"s3://{self.bucket}/{key}"

    def get(self, key: str) -> bytes:
        body: bytes = self.client.get_object(Bucket=self.bucket, Key=key)["Body"].read()
        return body


class ArtifactIndex(Protocol):
    """Rows in `artifacts` (and `artifact_quarantine`)."""

    def find(self, sha256: str, tenant_id: UUID | None) -> StoredArtifact | None: ...

    def insert(
        self,
        artifact: StoredArtifact,
        tenant_id: UUID | None,
        classification: DataClassification,
    ) -> StoredArtifact: ...

    def quarantine(self, sha256: str, reason: str, source_ref: str | None) -> None: ...


@dataclass
class InMemoryArtifactIndex:
    rows: dict[tuple[str, UUID | None], StoredArtifact] = field(default_factory=dict)
    quarantined: list[tuple[str, str, str | None]] = field(default_factory=list)

    def find(self, sha256: str, tenant_id: UUID | None) -> StoredArtifact | None:
        return self.rows.get((sha256, tenant_id))

    def insert(
        self,
        artifact: StoredArtifact,
        tenant_id: UUID | None,
        classification: DataClassification,
    ) -> StoredArtifact:
        return self.rows.setdefault((artifact.sha256, tenant_id), artifact)

    def quarantine(self, sha256: str, reason: str, source_ref: str | None) -> None:
        self.quarantined.append((sha256, reason, source_ref))


def blob_key(sha256: str) -> str:
    return f"sha256/{sha256[:2]}/{sha256}"


@dataclass
class ArtifactStore:
    blobs: BlobStore
    index: ArtifactIndex
    allowed: frozenset[str] = ALLOWED_MEDIA_TYPES

    def put(
        self,
        data: bytes,
        *,
        filename: str | None = None,
        source_ref: str | None = None,
        tenant_id: UUID | None = None,
        classification: DataClassification = "public",
    ) -> StoredArtifact:
        digest = sha256_hex(data)
        reason = self._rejection(data)
        if reason is not None:
            self.index.quarantine(digest, reason, source_ref or filename)
            raise ArtifactRejectedError(reason, digest)
        existing = self.index.find(digest, tenant_id)
        if existing is not None:
            return existing
        media_type = sniff_media_type(data) or ""
        uri = self.blobs.put(blob_key(digest), data, media_type)
        artifact = StoredArtifact(
            artifact_id=str(_artifact_uuid(digest, tenant_id)),
            sha256=digest,
            storage_uri=uri,
            media_type=media_type,
            size=len(data),
            filename=filename,
        )
        return self.index.insert(artifact, tenant_id, classification)

    def read(self, artifact: StoredArtifact) -> bytes:
        return self.blobs.get(blob_key(artifact.sha256))

    def _rejection(self, data: bytes) -> str | None:
        if not data:
            return "empty_file"
        media_type = sniff_media_type(data)
        if media_type is None or media_type not in self.allowed:
            return f"file_type_not_allowed:{media_type or 'unknown'}"
        try:
            return active_content_reason(data, media_type)
        except (zipfile.BadZipFile, KeyError):
            return "corrupt_container"


def _artifact_uuid(sha256: str, tenant_id: UUID | None) -> UUID:
    """Deterministic id so the same bytes always map to the same artifact per tenant."""
    scope = str(tenant_id) if tenant_id else "public"
    return UUID(hashlib.sha256(f"{scope}:{sha256}".encode()).hexdigest()[:32], version=5)
