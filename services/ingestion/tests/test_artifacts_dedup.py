from __future__ import annotations

import io
import zipfile

import pytest
from hope_ingestion.artifacts import (
    DOCX,
    PDF,
    ArtifactRejectedError,
    ArtifactStore,
    InMemoryArtifactIndex,
    InMemoryBlobStore,
    sha256_hex,
)
from hope_ingestion.dedup import NearDuplicateIndex
from hope_ingestion.testing import RFP_PAGES, make_docx, make_pdf


def store() -> tuple[ArtifactStore, InMemoryArtifactIndex, InMemoryBlobStore]:
    blobs, index = InMemoryBlobStore(), InMemoryArtifactIndex()
    return ArtifactStore(blobs, index), index, blobs


def test_content_addressed_and_idempotent() -> None:
    artifacts, index, blobs = store()
    data = make_pdf(RFP_PAGES)
    first = artifacts.put(data, filename="a.pdf")
    second = artifacts.put(data, filename="copy.pdf")
    assert first == second
    assert first.sha256 == sha256_hex(data)
    assert first.media_type == PDF
    assert first.storage_uri == f"s3://hope-artifacts/sha256/{first.sha256[:2]}/{first.sha256}"
    assert len(blobs.blobs) == 1 and len(index.rows) == 1
    assert artifacts.read(first) == data
    assert artifacts.put(make_docx(["Hello grant world"])).media_type == DOCX


@pytest.mark.parametrize(
    ("data", "reason"),
    [
        (b"MZ\x90\x00\x03binary", "file_type_not_allowed:unknown"),
        (b"", "empty_file"),
        (
            make_pdf(
                [["hi"]], catalog_extra="/OpenAction << /S /JavaScript /JS (app.alert(1)) >> "
            ),
            "pdf_active_content:JavaScript",
        ),
        (
            make_pdf([["hi"]]).replace(b"/Root 1 0 R", b"/Root 1 0 R /Encrypt 9 0 R"),
            "pdf_encrypted",
        ),
    ],
)
def test_rejects_disallowed_and_active_content(data: bytes, reason: str) -> None:
    artifacts, index, _ = store()
    with pytest.raises(ArtifactRejectedError) as err:
        artifacts.put(data, filename="bad")
    assert err.value.reason == reason
    assert index.quarantined[0][1] == reason
    assert not index.rows


def test_rejects_macro_docx_and_plain_zip() -> None:
    buffer = io.BytesIO(make_docx(["macro"]))
    with zipfile.ZipFile(buffer, "a") as archive:
        archive.writestr("word/vbaProject.bin", b"\x00vba")
    artifacts, _, _ = store()
    with pytest.raises(ArtifactRejectedError, match="docx_active_content"):
        artifacts.put(buffer.getvalue())
    plain = io.BytesIO()
    with zipfile.ZipFile(plain, "w") as archive:
        archive.writestr("payload.exe", b"x")
    with pytest.raises(ArtifactRejectedError, match="file_type_not_allowed"):
        artifacts.put(plain.getvalue())


def test_near_duplicate_detection() -> None:
    text = " ".join(" ".join(page) for page in RFP_PAGES)
    index = NearDuplicateIndex(threshold=0.8)
    values = index.add("opp-1", text)
    assert len(values) == index.num_perm
    cross_posted = text.replace("Riverbend Community Foundation", "Riverbend Community Fdn")
    matches = index.similar(cross_posted)
    assert matches and matches[0][0] == "opp-1"
    assert index.similar(cross_posted, exclude="opp-1") == []
    assert index.similar("Arts council funding for public murals in Oregon cities") == []
    restored = NearDuplicateIndex(threshold=0.8)
    restored.add_signature("opp-1", values)
    assert restored.similar(text)[0][0] == "opp-1"
