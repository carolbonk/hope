"""A1 -> A2 pipeline: store raw artifacts, dedup, parse, apply the missing-field policy,
persist a version and emit opportunity events to the pillar."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal
from uuid import UUID, uuid4

from hope_core.envelope import PillarEnvelope, Producer
from hope_core.hashing import canonical_json
from hope_core.model_gateway import ModelGateway, RunBudget
from hope_core.pillar import PillarPort
from hope_core.schemas.grant_opportunity import GrantOpportunity, PipelinePath, Source
from hope_core.topics import EventType

from hope_ingestion.artifacts import ArtifactRejectedError, ArtifactStore, StoredArtifact
from hope_ingestion.connectors.base import (
    ArtifactRef,
    Cursor,
    RawRecord,
    SavedSearch,
    SourceConnector,
    SourceFacts,
)
from hope_ingestion.contracts import (
    ArtifactSummary,
    BlockingIssue,
    Candidate,
    OpportunityAmended,
    ParseIncomplete,
    QuarantineNotice,
    RawIngested,
    schema_ref,
)
from hope_ingestion.dedup import NearDuplicateIndex
from hope_ingestion.parsing.extraction import PROMPT_VERSION, Finding, SectionExtractor
from hope_ingestion.parsing.injection import injection_signals, strip_invisible
from hope_ingestion.parsing.ocr import NoOcr, OcrEngine
from hope_ingestion.parsing.sections import split_sections
from hope_ingestion.parsing.text import (
    CorruptDocumentError,
    DocumentText,
    extract_text,
    text_quality_ok,
)
from hope_ingestion.policy import apply_policy, field_diff
from hope_ingestion.repository import OpportunityRepository

SERVICE = "ingestion"
Document = tuple[ArtifactRef | None, bytes]


@dataclass
class IngestResult:
    status: Literal["normalized", "parse_incomplete", "unchanged"]
    opportunity: GrantOpportunity | None = None
    version: int | None = None
    blocking: list[BlockingIssue] = field(default_factory=list)
    events: list[PillarEnvelope] = field(default_factory=list)


@dataclass
class _Parsed:
    texts: list[DocumentText] = field(default_factory=list)
    stored: list[StoredArtifact] = field(default_factory=list)
    quarantined: list[QuarantineNotice] = field(default_factory=list)
    blocking: list[BlockingIssue] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    path: list[PipelinePath] = field(default_factory=list)


@dataclass
class IngestionPipeline:
    pillar: PillarPort
    gateway: ModelGateway
    artifacts: ArtifactStore
    repository: OpportunityRepository
    near_duplicates: NearDuplicateIndex = field(default_factory=NearDuplicateIndex)
    ocr: OcrEngine = field(default_factory=NoOcr)
    budget_factory: type[RunBudget] = RunBudget

    def __post_init__(self) -> None:
        for opportunity_id, values in self.repository.signatures():
            self.near_duplicates.add_signature(str(opportunity_id), values)

    def run(
        self, connector: SourceConnector, query: SavedSearch, cursor: Cursor | None = None
    ) -> tuple[list[IngestResult], Cursor]:
        results: list[IngestResult] = []
        position = cursor or Cursor()
        for record in connector.discover(position, query):
            refs = connector.fetch_artifacts(record)
            documents: list[Document] = [(ref, connector.download(ref)) for ref in refs]
            results.append(self.ingest(record, documents, connector.facts(record)))
            position = record.cursor
        return results, position

    def ingest(
        self, record: RawRecord, documents: list[Document], facts: SourceFacts | None = None
    ) -> IngestResult:
        previous = self.repository.latest(record.source_system, record.source_id)
        opportunity_id = previous.opportunity_id if previous else uuid4()
        parsed = _Parsed()
        facts_artifact = self._store_metadata(record, parsed) if facts else None
        for ref, data in documents:
            self._store_document(ref, data, parsed)

        raw = self._envelope(
            EventType.OPPORTUNITY_RAW_INGESTED,
            opportunity_id,
            RawIngested(
                source_system=record.source_system,
                source_id=record.source_id,
                revision=record.revision,
                url=record.url,
                artifacts=[
                    ArtifactSummary(
                        artifact_id=a.artifact_id,
                        sha256=a.sha256,
                        media_type=a.media_type,
                        filename=a.filename,
                    )
                    for a in parsed.stored
                ],
                quarantined=parsed.quarantined,
            ),
            "raw-ingested",
            agent_id="A1",
        )
        artifact_ids = sorted({a.artifact_id for a in parsed.stored})
        if previous and sorted(previous.normalized["source"]["artifact_ids"]) == artifact_ids:
            return IngestResult("unchanged", version=previous.version)
        self.pillar.publish(raw)
        events = [raw]

        texts = [t for t in parsed.texts if t.media_type != "application/json"]
        full_text = "\n".join(t.text for t in texts)
        hidden = [h for t in texts for h in t.hidden_text]
        injection = injection_signals(full_text, hidden)
        extractor = SectionExtractor(self.gateway, budget=self.budget_factory())
        findings: list[Finding] = []
        for doc in texts:
            clean = DocumentText(
                doc.artifact_id,
                doc.media_type,
                [type(p)(p.number, strip_invisible(p.text)) for p in doc.pages],
                doc.hidden_text,
                doc.pipeline_path,
            )
            findings += extractor.extract(split_sections(clean))
        if extractor.budget_exceeded:
            parsed.blocking.append(
                BlockingIssue(field="parse_quality.model_budget_exceeded", reason="unreadable")
            )
        if injection:
            parsed.blocking.append(
                BlockingIssue(
                    field="parse_quality.injection_suspected",
                    reason="unreadable",
                    candidates=[Candidate(value=s) for s in injection],
                )
            )

        dup_key = str(opportunity_id)
        if full_text.strip():
            for other, score in self.near_duplicates.similar(full_text, exclude=dup_key):
                parsed.warnings.append(f"near_duplicate_of:{other}:{score:.2f}")

        amendment_seq = previous.amendment_seq + 1 if previous else 0
        result = apply_policy(
            opportunity_id=opportunity_id,
            source=Source(
                system=record.source_system,
                source_id=record.source_id,
                url=record.url,
                artifact_ids=artifact_ids,
                amendment_seq=amendment_seq,
            ),
            findings=findings,
            facts=facts,
            facts_artifact_id=facts_artifact,
            full_text=full_text,
            pipeline_path=parsed.path or ["native_text"],
            injection=injection,
            warnings=parsed.warnings,
            blocking=parsed.blocking,
        )
        stored = self.repository.save(result.opportunity)
        if full_text.strip():
            values = self.near_duplicates.add(dup_key, full_text)
            self.repository.save_signature(opportunity_id, self.near_duplicates.num_perm, values)

        if previous:
            changes = field_diff(previous.normalized, stored.normalized)
            amended = OpportunityAmended(
                opportunity_id=opportunity_id,
                from_version=previous.version,
                to_version=stored.version,
                amendment_seq=amendment_seq,
                changes=changes,
            )
            events.append(self._follow(raw, EventType.OPPORTUNITY_AMENDED, amended, "amended"))

        if result.blocking:
            payload: Any = ParseIncomplete(
                opportunity=result.opportunity,
                version=stored.version,
                blocking=result.blocking,
                questions_to_funder=result.questions_to_funder,
            )
            events.append(
                self._follow(
                    raw, EventType.OPPORTUNITY_PARSE_INCOMPLETE, payload, "parse-incomplete"
                )
            )
            status: Literal["normalized", "parse_incomplete"] = "parse_incomplete"
        else:
            events.append(
                self._follow(
                    raw, EventType.OPPORTUNITY_NORMALIZED, result.opportunity, "grant-opportunity"
                )
            )
            status = "normalized"
        for event in events[1:]:
            self.pillar.publish(event)
        return IngestResult(status, result.opportunity, stored.version, result.blocking, events)

    def _store_metadata(self, record: RawRecord, parsed: _Parsed) -> str | None:
        data = canonical_json(record.metadata).encode()
        artifact = self.artifacts.put(
            data, filename=f"{record.source_id}.metadata.json", source_ref=record.url
        )
        parsed.stored.append(artifact)
        return artifact.artifact_id

    def _store_document(self, ref: ArtifactRef | None, data: bytes, parsed: _Parsed) -> None:
        filename = ref.filename if ref else None
        try:
            artifact = self.artifacts.put(
                data, filename=filename, source_ref=ref.url if ref else None
            )
        except ArtifactRejectedError as exc:
            parsed.quarantined.append(
                QuarantineNotice(sha256=exc.sha256, reason=exc.reason, filename=filename)
            )
            parsed.blocking.append(
                BlockingIssue(
                    field="source.artifacts",
                    reason="corrupt",
                    candidates=[Candidate(value=f"{filename or exc.sha256}: {exc.reason}")],
                )
            )
            return
        parsed.stored.append(artifact)
        try:
            doc = extract_text(data, artifact.media_type, artifact.artifact_id)
        except CorruptDocumentError as exc:
            parsed.blocking.append(
                BlockingIssue(
                    field="source.artifacts",
                    reason="corrupt",
                    candidates=[Candidate(value=f"{filename or artifact.artifact_id}: {exc}")],
                )
            )
            return
        parsed.path.append("native_text")
        if not text_quality_ok(doc):
            parsed.path.append("ocr")
            recognized = self.ocr.recognize(data, doc)
            if recognized is None:
                parsed.warnings.append(f"ocr_fallback_not_implemented:{artifact.artifact_id}")
                parsed.blocking.append(
                    BlockingIssue(
                        field="source.artifacts",
                        reason="unreadable",
                        candidates=[Candidate(value=f"{filename or artifact.artifact_id}")],
                    )
                )
                return
            doc = recognized
        parsed.texts.append(doc)

    def _envelope(
        self,
        event_type: EventType,
        opportunity_id: UUID,
        payload: Any,
        schema: str,
        agent_id: str = "A2",
    ) -> PillarEnvelope:
        return PillarEnvelope(
            event_type=event_type,
            schema_ref=schema_ref(schema),
            subject_id=str(opportunity_id),
            producer=self._producer(agent_id),
            data_classification="public",
            payload=payload.model_dump(mode="json"),
        )

    def _follow(
        self, cause: PillarEnvelope, event_type: EventType, payload: Any, schema: str
    ) -> PillarEnvelope:
        return cause.caused(
            event_type=event_type,
            schema_ref=schema_ref(schema),
            producer=self._producer("A2"),
            payload=payload.model_dump(mode="json"),
        )

    def _producer(self, agent_id: str) -> Producer:
        return Producer(
            service=SERVICE,
            agent_id=agent_id,
            model_ids=[p.name for p in self.gateway.providers],
            prompt_version=PROMPT_VERSION if agent_id == "A2" else None,
        )
