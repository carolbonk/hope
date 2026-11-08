"""Application routes (H6): the server-side application record, its stage gates, eligibility
evidence, simulated approvals and activity (step 1); the grant's own requirements read from its
pages or pasted by staff (step 2); per-question drafts, edits, checklist and export (step 3).
Hope never submits to a funder."""

from __future__ import annotations

import base64
import binascii
from datetime import date, datetime
from typing import Annotated, Any, Literal, NoReturn
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Response
from fastapi.responses import PlainTextResponse
from hope_core import jobs, store
from hope_core.auth import Principal, ProblemException, get_principal
from hope_core.db import connect, tenant_tx
from hope_core.money import Money
from hope_core.settings import get_settings
from hope_core.store import Tx
from hope_core.web import parse_pdf
from hope_discovery.answers import (
    TO_CONFIRM,
    Answer,
    AnswerDrafter,
    Checklist,
    GrantContext,
    build_checklist,
    effective_questions,
    export_markdown,
)
from hope_discovery.glossary import TermExplained, explain
from hope_discovery.requirements import Question, Requirements, RequirementsReader
from hope_discovery.runner import default_tools
from psycopg.types.json import Jsonb
from pydantic import BaseModel, ConfigDict, Field

router = APIRouter(prefix="/v1", tags=["applications"])

Stage = Literal["saved", "eligibility", "approval", "drafting", "ready"]
Step = Literal["program", "director"]
EvidenceStatus = Literal["yes", "no", "unknown"]
QuestionsStatus = Literal["unread", "reading", "found", "not_found"]
EventKind = Literal[
    "created",
    "stage",
    "comment",
    "evidence",
    "approval",
    "send_back",
    "requirements",
    "draft",
    "edit",
    "fact",
]

EVENTS_SHOWN = 50
REQUIREMENTS_KIND = "requirements"
ANSWERS_KIND = "answers"
MAX_PASTE = 60_000
MAX_PDF = 8_000_000
# Stage moves a caller may ask for; approval -> drafting happens only via director approval.
MOVES: dict[tuple[str, str], str | None] = {
    ("saved", "eligibility"): None,
    ("eligibility", "approval"): "Resolve unknown or failed requirements first.",
    ("drafting", "ready"): "Both reviews must approve first.",
    ("ready", "drafting"): None,
}


class Approval(BaseModel):
    by: UUID
    at: datetime
    comment: str | None = None


class Evidence(BaseModel):
    status: EvidenceStatus
    note: str | None = None
    by: UUID
    at: datetime


class EventView(BaseModel):
    kind: EventKind
    actor: UUID | None
    payload: dict[str, Any]
    at: datetime


class RequirementsJob(BaseModel):
    job_id: UUID
    status: str
    error: str | None
    result: dict[str, Any] | None = None
    started_at: datetime | None
    finished_at: datetime | None


class ApplicationSummary(BaseModel):
    application_id: UUID
    grant_id: UUID
    title: str
    funder: str
    url: str
    deadline: date | None
    deadline_text: str | None
    stage: Stage
    questions_status: QuestionsStatus
    updated_at: datetime


class AnswerView(BaseModel):
    question_key: str
    text: str
    origin: Literal["ai", "template", "human"]
    model: str | None
    prompt_version: str | None
    citations: list[dict[str, Any]]
    to_confirm: list[str]
    updated_by: UUID | None
    updated_at: datetime


class FactView(BaseModel):
    need: str
    answer: str
    updated_by: UUID | None
    updated_at: datetime


class ApplicationView(ApplicationSummary):
    version: int
    requirements: Requirements | None
    requirements_job: RequirementsJob | None
    questions: list[Question]
    answers: list[AnswerView]
    facts: list[FactView]
    terms: list[TermExplained] = Field(
        description="Funder jargon in plain language, most urgent first, each with its source"
    )
    answers_job: RequirementsJob | None
    checklist: Checklist
    ask: Money | None
    approvals: dict[Step, Approval]
    evidence: dict[str, Evidence]
    events: list[EventView]
    created_at: datetime


class ApplicationList(BaseModel):
    items: list[ApplicationSummary]
    total: int


class StageBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    to: Stage
    override_reason: str | None = Field(None, min_length=10, max_length=500)


class PasteBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str | None = Field(None, min_length=20, max_length=MAX_PASTE)
    pdf_base64: str | None = Field(None, max_length=MAX_PDF * 4 // 3 + 4)


class DraftBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    confirm_overwrite: bool = False


class FactBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    need: str = Field(min_length=1, max_length=300)
    answer: str = Field("", max_length=4000, description="Empty removes the fact")


class AnswerBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(max_length=20_000)


class EvidenceBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    requirement_id: str = Field(min_length=1, max_length=80)
    status: EvidenceStatus
    note: str | None = Field(None, max_length=500)


class ApprovalBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    step: Step
    decision: Literal["approve", "send_back"]
    comment: str | None = Field(None, max_length=1000)


class CommentBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(min_length=1, max_length=2000)


# --- store ------------------------------------------------------------------------------------

_SELECT = (
    "SELECT a.*, g.title, g.funder, g.url, g.summary, g.deadline, g.deadline_text"
    " FROM applications a JOIN grant_candidates g USING (grant_id)"
)


def add_event(
    tx: Tx, application_id: UUID, kind: EventKind, actor: UUID | None, **payload: Any
) -> None:
    tx.execute(
        "INSERT INTO application_events (application_id, tenant_id, kind, actor, payload)"
        " VALUES (%s, current_tenant(), %s, %s, %s)",
        (application_id, kind, actor, Jsonb(payload)),
    )


def ensure_application(tx: Tx, grant_id: UUID, actor: UUID | None) -> UUID:
    """The one application for a grant; saving again (after pass or reset) reuses it."""
    tx.execute(
        "INSERT INTO applications (tenant_id, grant_id, created_by)"
        " VALUES (current_tenant(), %s, %s)"
        " ON CONFLICT (tenant_id, grant_id) DO NOTHING RETURNING application_id",
        (grant_id, actor),
    )
    row = tx.fetchone()
    if row is not None:
        add_event(tx, row["application_id"], "created", actor)
        return UUID(str(row["application_id"]))
    tx.execute("SELECT application_id FROM applications WHERE grant_id = %s", (grant_id,))
    found = tx.fetchone()
    assert found is not None
    return UUID(str(found["application_id"]))


def _row(tx: Tx, application_id: UUID) -> dict[str, Any]:
    tx.execute(f"{_SELECT} WHERE a.application_id = %s", (application_id,))
    row = tx.fetchone()
    if row is None:
        _not_found()
    return row


def _view(tx: Tx, row: dict[str, Any]) -> ApplicationView:
    tx.execute(
        "SELECT kind, actor, payload, at FROM application_events"
        " WHERE application_id = %s ORDER BY at DESC LIMIT %s",
        (row["application_id"], EVENTS_SHOWN),
    )
    events = [EventView.model_validate(e) for e in tx.fetchall()]
    requirements = latest_requirements(tx, row["application_id"])
    answers = load_answers(tx, row["application_id"])
    facts = load_facts(tx, row["application_id"])
    terms = explain(
        requirements.terms if requirements else [],
        store.get_profile(tx),
        requirements.submission.deadline_date if requirements else None,
        datetime.now().astimezone().date(),
    )
    job = store.latest_job(tx, REQUIREMENTS_KIND, str(row["application_id"]))
    answers_job = store.latest_job(tx, ANSWERS_KIND, str(row["application_id"]))
    ask = (
        Money(amount_minor=row["ask_minor"], currency=row["currency"]) if row["ask_minor"] else None
    )
    return ApplicationView.model_validate(
        row
        | {
            "ask": ask,
            "events": events,
            "requirements": requirements,
            "requirements_job": job.model_dump() if job else None,
            "questions": effective_questions(requirements),
            "answers": list(answers.values()),
            "facts": list(facts.values()),
            "terms": terms,
            "answers_job": answers_job.model_dump() if answers_job else None,
            "checklist": checklist_for(requirements, answers, facts, terms),
        }
    )


def latest_requirements(tx: Tx, application_id: UUID) -> Requirements | None:
    tx.execute(
        "SELECT questions, attachments, budget, submission, eligibility, terms, pages"
        " FROM application_requirements WHERE application_id = %s"
        " ORDER BY revision DESC LIMIT 1",
        (application_id,),
    )
    req = tx.fetchone()
    return Requirements.model_validate(req) if req else None


def load_answers(tx: Tx, application_id: UUID) -> dict[str, AnswerView]:
    tx.execute(
        "SELECT question_key, text, origin, model, prompt_version, citations, to_confirm,"
        " updated_by, updated_at FROM application_answers WHERE application_id = %s"
        " ORDER BY updated_at",
        (application_id,),
    )
    return {r["question_key"]: AnswerView.model_validate(r) for r in tx.fetchall()}


def load_facts(tx: Tx, application_id: UUID) -> dict[str, FactView]:
    tx.execute(
        "SELECT need, answer, updated_by, updated_at FROM application_facts"
        " WHERE application_id = %s ORDER BY updated_at",
        (application_id,),
    )
    return {r["need"]: FactView.model_validate(r) for r in tx.fetchall()}


def checklist_for(
    req: Requirements | None,
    answers: dict[str, AnswerView],
    facts: dict[str, FactView] | None = None,
    terms: list[TermExplained] | None = None,
) -> Checklist:
    plain = {k: Answer.model_validate(a.model_dump()) for k, a in answers.items()}
    given = {k: f.answer for k, f in (facts or {}).items()}
    return build_checklist(req, plain, datetime.now().astimezone().date(), given, terms)


def _update(tx: Tx, application_id: UUID, version: int, **fields: Any) -> None:
    """Optimistic write: bumps `version`, or 412 when the caller's copy is stale."""
    sets = ", ".join(f"{k} = %s" for k in fields)
    values = [Jsonb(v) if isinstance(v, dict) else v for v in fields.values()]
    tx.execute(
        f"UPDATE applications SET {sets}{', ' if sets else ''}version = version + 1,"
        " updated_at = clock_timestamp() WHERE application_id = %s AND version = %s",
        (*values, application_id, version),
    )
    if tx.rowcount == 0:
        raise ProblemException(412, "version_mismatch", "This application changed; reload it")


# --- rules (code decides) ---------------------------------------------------------------------


def move_problem(row: dict[str, Any], to: str) -> str | None:
    """Why `row` can't move to stage `to`, or None when it can."""
    key = (row["stage"], to)
    if key not in MOVES:
        return f"Can't move from {row['stage']} to {to}."
    if to == "approval" and any(e["status"] != "yes" for e in row["evidence"].values()):
        return MOVES[key]
    if to == "ready" and set(row["approvals"]) != {"program", "director"}:
        return MOVES[key]
    return None


def ready_problem(checklist: Checklist) -> str | None:
    """Ready means every question answered within its limit, nothing to confirm, no upload
    missing and the deadline not passed; staff can override with a written reason."""
    if checklist.complete:
        return None
    open_items = [i.label for i in checklist.items if i.status in READY_BLOCKERS]
    return "Finish the checklist first: " + "; ".join(x[:60] for x in open_items[:5])


READY_BLOCKERS = {"missing", "over_limit", "to_confirm", "upload_needed", "passed"}


# --- helpers ----------------------------------------------------------------------------------


def _not_found() -> NoReturn:
    raise ProblemException(404, "application_not_found", "Application not found")


def _blocked(reason: str) -> NoReturn:
    raise ProblemException(
        409,
        "stage_blocked",
        "Stage blocked",
        [{"field": "stage", "code": "blocked", "message": reason}],
    )


def _app_uuid(application_id: str) -> UUID:
    try:
        return UUID(application_id)
    except ValueError:
        _not_found()


def _version(if_match: str | None) -> int:
    if if_match is None:
        raise ProblemException(428, "if_match_required", "If-Match required")
    try:
        return int(if_match.removeprefix("W/").strip().strip('"'))
    except ValueError:
        raise ProblemException(400, "invalid_if_match", "If-Match must be a version") from None


def _respond(tx: Tx, application_id: UUID, response: Response) -> ApplicationView:
    view = _view(tx, _row(tx, application_id))
    response.headers["ETag"] = f'"{view.version}"'
    return view


PrincipalDep = Annotated[Principal, Depends(get_principal)]
IfMatch = Annotated[str | None, Header()]


# --- routes -----------------------------------------------------------------------------------


@router.get("/applications")
def list_applications(principal: PrincipalDep) -> ApplicationList:
    with connect() as conn, tenant_tx(conn, principal.tenant_id) as tx:
        tx.execute(f"{_SELECT} ORDER BY g.deadline NULLS LAST, a.updated_at DESC")
        items = [ApplicationSummary.model_validate(r) for r in tx.fetchall()]
    return ApplicationList(items=items, total=len(items))


@router.get("/applications/{application_id}")
def get_application(
    application_id: str, principal: PrincipalDep, response: Response
) -> ApplicationView:
    aid = _app_uuid(application_id)
    with connect() as conn, tenant_tx(conn, principal.tenant_id) as tx:
        return _respond(tx, aid, response)


@router.post("/applications/{application_id}/stage")
def move_stage(
    application_id: str,
    body: StageBody,
    principal: PrincipalDep,
    response: Response,
    if_match: IfMatch = None,
) -> ApplicationView:
    aid, version = _app_uuid(application_id), _version(if_match)
    with connect() as conn, tenant_tx(conn, principal.tenant_id) as tx:
        row = _row(tx, aid)
        if reason := move_problem(row, body.to):
            _blocked(reason)
        override = None
        if body.to == "ready":
            req = latest_requirements(tx, aid)
            gap = ready_problem(checklist_for(req, load_answers(tx, aid)))
            if gap and not body.override_reason:
                _blocked(gap)
            override = body.override_reason if gap else None
        _update(tx, aid, version, stage=body.to)
        payload: dict[str, Any] = {"from": row["stage"], "to": body.to}
        if override:
            payload["override_reason"] = override
        add_event(tx, aid, "stage", principal.user_id, **payload)
        return _respond(tx, aid, response)


@router.post("/applications/{application_id}/evidence")
def record_evidence(
    application_id: str,
    body: EvidenceBody,
    principal: PrincipalDep,
    response: Response,
    if_match: IfMatch = None,
) -> ApplicationView:
    aid, version = _app_uuid(application_id), _version(if_match)
    with connect() as conn, tenant_tx(conn, principal.tenant_id) as tx:
        row = _row(tx, aid)
        if row["stage"] not in ("saved", "eligibility"):
            _blocked("Eligibility is locked once the application is in review.")
        item = Evidence(
            status=body.status, note=body.note, by=principal.user_id, at=datetime.now().astimezone()
        )
        evidence = row["evidence"] | {body.requirement_id: item.model_dump(mode="json")}
        _update(tx, aid, version, evidence=evidence)
        add_event(
            tx,
            aid,
            "evidence",
            principal.user_id,
            requirement_id=body.requirement_id,
            status=body.status,
        )
        return _respond(tx, aid, response)


@router.post("/applications/{application_id}/approvals")
def review(
    application_id: str,
    body: ApprovalBody,
    principal: PrincipalDep,
    response: Response,
    if_match: IfMatch = None,
) -> ApplicationView:
    """Simulated internal review: program, then director. Never a funder decision."""
    aid, version = _app_uuid(application_id), _version(if_match)
    with connect() as conn, tenant_tx(conn, principal.tenant_id) as tx:
        row = _row(tx, aid)
        if row["stage"] != "approval":
            _blocked("Send the application to internal approval first.")
        if body.decision == "send_back":
            if not (body.comment or "").strip():
                raise ProblemException(
                    422, "comment_required", "Add a comment explaining what to change."
                )
            _update(tx, aid, version, stage="eligibility", approvals={})
            add_event(tx, aid, "send_back", principal.user_id, step=body.step, comment=body.comment)
            return _respond(tx, aid, response)
        if body.step == "director" and "program" not in row["approvals"]:
            _blocked("Program review must approve first.")
        item = Approval(by=principal.user_id, at=datetime.now().astimezone(), comment=body.comment)
        approvals = row["approvals"] | {body.step: item.model_dump(mode="json")}
        stage = "drafting" if body.step == "director" else row["stage"]
        _update(tx, aid, version, approvals=approvals, stage=stage)
        add_event(tx, aid, "approval", principal.user_id, step=body.step)
        return _respond(tx, aid, response)


@router.post("/applications/{application_id}/comments")
def comment(
    application_id: str, body: CommentBody, principal: PrincipalDep, response: Response
) -> ApplicationView:
    """Comments append to the activity log and don't change the version."""
    aid = _app_uuid(application_id)
    with connect() as conn, tenant_tx(conn, principal.tenant_id) as tx:
        _row(tx, aid)
        add_event(tx, aid, "comment", principal.user_id, text=body.text)
        return _respond(tx, aid, response)


# --- requirements (H6 step 2) -----------------------------------------------------------------


def run_requirements(application_id: UUID, grant_url: str) -> dict[str, Any]:
    """Job body: read the funder's pages, then store a new requirements revision."""
    gateway, web = default_tools()
    req = RequirementsReader(gateway, web).read(grant_url)
    with connect() as conn, tenant_tx(conn, get_settings().tenant_id) as tx:
        if previous := latest_requirements(tx, application_id):
            known = {q.key for q in req.questions}
            req.questions += [
                q for q in previous.questions if q.source == "pasted" and q.key not in known
            ]
        save_requirements(tx, application_id, req)
        status = "found" if req.questions else "not_found"
        counts = {
            "questions": len(req.questions),
            "attachments": len(req.attachments),
            "pages_read": sum(p.status == "read" for p in req.pages),
            "pages_failed": sum(p.status == "failed" for p in req.pages),
        }
        add_event(tx, application_id, "requirements", None, status=status, **counts)
    return {"status": status, **counts}


def save_requirements(tx: Tx, application_id: UUID, req: Requirements) -> None:
    """A new revision; answers are keyed by question, so they stay linked across revisions."""
    data = req.model_dump(mode="json")
    tx.execute(
        "INSERT INTO application_requirements (application_id, tenant_id, revision, questions,"
        " attachments, budget, submission, eligibility, terms, pages)"
        " SELECT %s, current_tenant(), coalesce(max(revision), 0) + 1, %s, %s, %s, %s, %s, %s, %s"
        " FROM application_requirements WHERE application_id = %s",
        (
            application_id,
            *(Jsonb(data[k]) for k in REQ_FIELDS),
            application_id,
        ),
    )
    tx.execute(
        "UPDATE applications SET questions_status = %s WHERE application_id = %s",
        ("found" if req.questions else "not_found", application_id),
    )


REQ_FIELDS = ("questions", "attachments", "budget", "submission", "eligibility", "terms", "pages")


@router.post("/applications/{application_id}/requirements/jobs", status_code=202)
def read_requirements(
    application_id: str, principal: PrincipalDep, response: Response
) -> ApplicationView:
    """Start (or restart) reading this grant's application requirements from its pages."""
    aid = _app_uuid(application_id)
    with connect() as conn, tenant_tx(conn, principal.tenant_id) as tx:
        row = _row(tx, aid)
        tx.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (f"requirements:{aid}",))
        running = store.latest_job(tx, REQUIREMENTS_KIND, str(aid))
        if running and running.status in ("queued", "running"):
            raise ProblemException(409, "job_running", "Requirements are already being read")
        job = store.create_job(tx, REQUIREMENTS_KIND, str(aid), principal.user_id)
        tx.execute(
            "UPDATE applications SET questions_status = 'reading' WHERE application_id = %s",
            (aid,),
        )
        url = row["url"]
    jobs.start_job(
        REQUIREMENTS_KIND,
        run_requirements,
        aid,
        url,
        job_id=job.job_id,
        created_by=principal.user_id,
    )
    with connect() as conn, tenant_tx(conn, principal.tenant_id) as tx:
        return _respond(tx, aid, response)


@router.post("/applications/{application_id}/requirements/paste")
def paste_requirements(
    application_id: str, body: PasteBody, principal: PrincipalDep, response: Response
) -> ApplicationView:
    """Staff paste the funder's form, or upload its PDF, when the questions sit behind a login."""
    aid = _app_uuid(application_id)
    if (body.text is None) == (body.pdf_base64 is None):
        raise ProblemException(422, "validation_failed", "Send either text or pdf_base64")
    text = body.text or _pdf_text(body.pdf_base64 or "")
    with connect() as conn, tenant_tx(conn, principal.tenant_id) as tx:
        _row(tx, aid)
        base = latest_requirements(tx, aid)
    gateway, web = default_tools()
    req = RequirementsReader(gateway, web).read_text(text, base)
    added = len(req.questions) - (len(base.questions) if base else 0)
    with connect() as conn, tenant_tx(conn, principal.tenant_id) as tx:
        _row(tx, aid)
        save_requirements(tx, aid, req)
        add_event(
            tx, aid, "requirements", principal.user_id, status="pasted", questions_added=added
        )
        return _respond(tx, aid, response)


def _pdf_text(data: str) -> str:
    try:
        raw = base64.b64decode(data, validate=True)
    except (binascii.Error, ValueError):
        raise ProblemException(422, "validation_failed", "pdf_base64 is not base64") from None
    if not raw.startswith(b"%PDF-") or len(raw) > MAX_PDF:
        raise ProblemException(422, "validation_failed", "Upload a PDF under 8 MB")
    try:
        text = parse_pdf(raw, "upload", "upload").text
    except Exception:
        raise ProblemException(422, "validation_failed", "Couldn't read that PDF") from None
    if len(text.strip()) < 20:
        raise ProblemException(422, "validation_failed", "That PDF has no readable text")
    return text[:MAX_PASTE]


def _question(tx: Tx, aid: UUID, key: str) -> tuple[Requirements | None, Question]:
    req = latest_requirements(tx, aid)
    found = next((q for q in effective_questions(req) if q.key == key), None)
    if found is None:
        raise ProblemException(404, "question_not_found", "Question not found")
    return req, found


def _draft_one(
    tx: Tx,
    aid: UUID,
    row: dict[str, Any],
    req: Requirements | None,
    q: Question,
    actor: UUID | None,
) -> None:
    profile = store.get_profile(tx)
    if profile is None:
        raise ProblemException(422, "profile_incomplete", "Finish your profile first")
    others = {k: a.text for k, a in load_answers(tx, aid).items()}
    facts = {k: f.answer for k, f in load_facts(tx, aid).items()}
    gateway, _web = default_tools()
    grant = GrantContext(row["title"], row["funder"], row["url"], row.get("summary") or "")
    result = AnswerDrafter(gateway).draft(
        profile, grant, req or Requirements(), q, others, facts=facts
    )
    tx.execute(
        "INSERT INTO application_answers (application_id, tenant_id, question_key, text, origin,"
        " model, prompt_version, citations, to_confirm, updated_by)"
        " VALUES (%s, current_tenant(), %s, %s, 'ai', %s, %s, %s, %s, %s)"
        " ON CONFLICT (application_id, question_key) DO UPDATE SET text = EXCLUDED.text,"
        " origin = 'ai', model = EXCLUDED.model, prompt_version = EXCLUDED.prompt_version,"
        " citations = EXCLUDED.citations, to_confirm = EXCLUDED.to_confirm,"
        " updated_by = EXCLUDED.updated_by, updated_at = clock_timestamp()",
        (
            aid,
            q.key,
            result.text,
            gateway.providers[0].name,
            result.prompt_version,
            Jsonb(result.citations),
            Jsonb(result.to_confirm),
            actor,
        ),
    )
    add_event(
        tx,
        aid,
        "draft",
        actor,
        question_key=q.key,
        over_limit=result.over_limit,
        to_confirm=len(result.to_confirm),
        unsupported_figures=result.unsupported,
        unsourced_sentences=len(result.unsourced),
    )


@router.post("/applications/{application_id}/answers/{question_key}/draft")
def draft_answer(
    application_id: str,
    question_key: str,
    principal: PrincipalDep,
    response: Response,
    body: DraftBody | None = None,
) -> ApplicationView:
    """Draft one answer to the funder's own question. A staff edit is never overwritten
    unless `confirm_overwrite` is set."""
    aid = _app_uuid(application_id)
    with connect() as conn, tenant_tx(conn, principal.tenant_id) as tx:
        row = _row(tx, aid)
        req, q = _question(tx, aid, question_key)
        current = load_answers(tx, aid).get(q.key)
        if current and current.origin == "human" and not (body and body.confirm_overwrite):
            raise ProblemException(
                409, "human_edit", "Staff edited this answer; confirm to replace it"
            )
        _draft_one(tx, aid, row, req, q, principal.user_id)
        return _respond(tx, aid, response)


def run_draft_all(application_id: UUID, actor: UUID | None) -> dict[str, Any]:
    """Job body: draft every unanswered question; staff edits and existing drafts are kept."""
    drafted = 0
    with connect() as conn, tenant_tx(conn, get_settings().tenant_id) as tx:
        row = _row(tx, application_id)
        req = latest_requirements(tx, application_id)
        done = load_answers(tx, application_id)
        todo = [q for q in effective_questions(req) if q.key not in done]
    for q in todo:
        with connect() as conn, tenant_tx(conn, get_settings().tenant_id) as tx:
            _draft_one(tx, application_id, row, req, q, actor)
        drafted += 1
        jobs.report({"drafted": drafted, "total": len(todo)})
    return {"drafted": drafted, "skipped": len(done)}


@router.post("/applications/{application_id}/answers/draft-all", status_code=202)
def draft_all(application_id: str, principal: PrincipalDep, response: Response) -> ApplicationView:
    aid = _app_uuid(application_id)
    with connect() as conn, tenant_tx(conn, principal.tenant_id) as tx:
        _row(tx, aid)
        if store.get_profile(tx) is None:
            raise ProblemException(422, "profile_incomplete", "Finish your profile first")
        tx.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (f"answers:{aid}",))
        running = store.latest_job(tx, ANSWERS_KIND, str(aid))
        if running and running.status in ("queued", "running"):
            raise ProblemException(409, "job_running", "Answers are already being drafted")
        job = store.create_job(tx, ANSWERS_KIND, str(aid), principal.user_id)
    jobs.start_job(
        ANSWERS_KIND,
        run_draft_all,
        aid,
        principal.user_id,
        job_id=job.job_id,
        created_by=principal.user_id,
    )
    with connect() as conn, tenant_tx(conn, principal.tenant_id) as tx:
        return _respond(tx, aid, response)


@router.patch("/applications/{application_id}/answers/{question_key}")
def edit_answer(
    application_id: str,
    question_key: str,
    body: AnswerBody,
    principal: PrincipalDep,
    response: Response,
    if_match: IfMatch = None,
) -> ApplicationView:
    """A staff edit. Bumps the application version so two editors can't silently collide."""
    aid, version = _app_uuid(application_id), _version(if_match)
    with connect() as conn, tenant_tx(conn, principal.tenant_id) as tx:
        _row(tx, aid)
        _req, q = _question(tx, aid, question_key)
        _update(tx, aid, version)
        tx.execute(
            "INSERT INTO application_answers (application_id, tenant_id, question_key, text,"
            " origin, to_confirm, updated_by)"
            " VALUES (%s, current_tenant(), %s, %s, 'human', %s, %s)"
            " ON CONFLICT (application_id, question_key) DO UPDATE SET text = EXCLUDED.text,"
            " origin = 'human', to_confirm = EXCLUDED.to_confirm, updated_by = EXCLUDED.updated_by,"
            " updated_at = clock_timestamp()",
            (aid, q.key, body.text, Jsonb(_open_confirms(body.text)), principal.user_id),
        )
        add_event(tx, aid, "edit", principal.user_id, question_key=q.key)
        return _respond(tx, aid, response)


@router.post("/applications/{application_id}/facts")
def supply_fact(
    application_id: str,
    body: FactBody,
    principal: PrincipalDep,
    response: Response,
    if_match: IfMatch = None,
) -> ApplicationView:
    """Staff answer a [TO CONFIRM] item once (e.g. the timeline); redrafts use it as a fact.
    Answers staff already edited stay as they are."""
    aid, version = _app_uuid(application_id), _version(if_match)
    need, answer = " ".join(body.need.split()), body.answer.strip()
    with connect() as conn, tenant_tx(conn, principal.tenant_id) as tx:
        _row(tx, aid)
        _update(tx, aid, version)
        if answer:
            tx.execute(
                "INSERT INTO application_facts (application_id, tenant_id, need, answer,"
                " updated_by) VALUES (%s, current_tenant(), %s, %s, %s)"
                " ON CONFLICT (application_id, need) DO UPDATE SET answer = EXCLUDED.answer,"
                " updated_by = EXCLUDED.updated_by, updated_at = clock_timestamp()",
                (aid, need, answer, principal.user_id),
            )
        else:
            tx.execute(
                "DELETE FROM application_facts WHERE application_id = %s AND need = %s",
                (aid, need),
            )
        add_event(tx, aid, "fact", principal.user_id, need=need, removed=not answer)
        return _respond(tx, aid, response)


def _open_confirms(text: str) -> list[str]:
    return [m.strip() for m in TO_CONFIRM.findall(text) if m.strip()]


@router.get("/applications/{application_id}/export.md", response_class=PlainTextResponse)
def export_application(application_id: str, principal: PrincipalDep) -> PlainTextResponse:
    """Every question with its limit and answer, attachments and deadline, ready to paste
    into the funder's own portal. Hope never submits."""
    aid = _app_uuid(application_id)
    with connect() as conn, tenant_tx(conn, principal.tenant_id) as tx:
        row = _row(tx, aid)
        req = latest_requirements(tx, aid)
        answers = {
            k: Answer.model_validate(a.model_dump()) for k, a in load_answers(tx, aid).items()
        }
    md = export_markdown(row["title"], row["funder"], row["url"], req, answers)
    return PlainTextResponse(md, media_type="text/markdown; charset=utf-8")
