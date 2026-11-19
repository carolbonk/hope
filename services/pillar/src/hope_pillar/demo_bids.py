"""Demo seed for My bids, run by `hope-demo-seed` after the discovery seed. Idempotent.

Saves three of the recorded real grants (`hope_discovery.demo_grants`) and opens a bid on each at
a different point: one still being prepared (mixed owners and statuses), one with its final review
done, and one submitted with a demo receipt. Hope never submits; the receipt is labelled as demo.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from urllib.parse import urlsplit
from uuid import UUID

from hope_core import store
from hope_core.db import connect, tenant_tx
from hope_core.money import Money
from hope_core.settings import get_settings
from hope_core.store import Tx
from hope_discovery.answers import ChecklistItem, standard_questions
from hope_discovery.demo_grants import (
    GRANTS,
    NCW_YOUTH,
    TITLE_X,
    YOUTH_TREATMENT,
    candidate,
    grant_id,
)
from hope_discovery.requirements import (
    BudgetRequirements,
    PageRead,
    Requirements,
    Sourced,
    Submission,
)
from psycopg.types.json import Jsonb

from hope_pillar.api.applications import add_event, ensure_application, save_requirements
from hope_pillar.api.bids import _load, item_hash
from hope_pillar.demo import DEMO_EMAIL

GRANTS_GOV_APPLY = (
    "How to apply: read the full notice and apply through the Grants.gov application."
)
FUNDER_APPLY = "How to apply: read the full notice and apply on the funder's website."
DEMO_RECEIPT = "DEMO-RECEIPT-0001 (demo record, not a real submission)"

# Riverbend's own draft answers to Hope's standard sections, in question order.
ANSWERS = (
    "The request expands Riverbend's bilingual community health worker network so more rural"
    " families get preventive and behavioral health care close to home.",
    "Riverbend brings preventive care, dental services and mental health support to rural families"
    " in north-central Washington regardless of ability to pay, which matches this program's aim.",
    "Chelan and Douglas counties are rural, and many farmworker families travel over an hour for"
    " care. Riverbend served 3,200 dental patients and 1,450 families through its health workers.",
    "Objectives: 400 more families connected to care in year one and 85% completing a follow-up"
    " visit, tracked in Riverbend's patient records and reported each quarter.",
    "The budget covers two community health worker positions, mileage for home visits and"
    " translation of outreach materials.",
    "Riverbend will keep the positions through Medicaid billing for community health worker"
    " services and its annual donor campaign.",
)

# grant URL → (ask in dollars, application stage, phase, answers written)
BIDS: dict[str, tuple[int, str, str, int]] = {
    TITLE_X: (350_000, "drafting", "preparing", 3),
    NCW_YOUTH: (1_000, "ready", "final_reviewed", 6),
    YOUTH_TREATMENT: (450_000, "submitted", "submitted", 6),
}


def _how_to_apply(url: str) -> str:
    return GRANTS_GOV_APPLY if urlsplit(url).hostname == "www.grants.gov" else FUNDER_APPLY


def _requirements(url: str) -> Requirements:
    spec = next(g for g in GRANTS if g["url"] == url)
    c = candidate(spec, datetime.now().astimezone().date(), datetime.now().astimezone())
    return Requirements(
        budget=BudgetRequirements(
            max_request=Sourced(text=spec["amount_text"], url=url),
            max_request_amount=c.amount_max,
        ),
        submission=Submission(
            method=Sourced(text=_how_to_apply(url), url=url),
            deadline=Sourced(text=spec["deadline_text"], url=url),
            deadline_date=c.deadline,
        ),
        pages=[PageRead(url=url, status="read")],
    )


def _item(
    tx: Tx, aid: UUID, key: str, owner: UUID | None, due: object, status: str, note: str = ""
) -> None:
    tx.execute(
        "INSERT INTO bid_items (application_id, tenant_id, item_key, owner, due, status, note,"
        " updated_by) VALUES (%s, current_tenant(), %s, %s, %s, %s, %s, %s)",
        (aid, key, owner, due, status, note, owner),
    )


def _seed_bid(tx: Tx, url: str, gid: UUID, user: UUID, now: datetime) -> None:
    ask, stage, phase, answered = BIDS[url]
    store.set_candidate_status(tx, gid, "saved", actor=user)
    aid = ensure_application(tx, gid, user)
    tx.execute(
        "UPDATE applications SET ask_minor = %s, stage = %s WHERE application_id = %s",
        (Money.from_decimal(ask).amount_minor, stage, aid),
    )
    save_requirements(tx, aid, _requirements(url))
    for q, text in list(zip(standard_questions(), ANSWERS, strict=True))[:answered]:
        tx.execute(
            "INSERT INTO application_answers (application_id, tenant_id, question_key, text,"
            " origin, updated_by) VALUES (%s, current_tenant(), %s, %s, 'human', %s)",
            (aid, q.key, text, user),
        )
    tx.execute(
        "INSERT INTO bids (application_id, tenant_id, created_by)"
        " VALUES (%s, current_tenant(), %s)",
        (aid, user),
    )
    add_event(tx, aid, "bid", user, action="started")
    view, _, checklist = _load(tx, aid)
    deadline = view.deadline
    keys = list(checklist)
    if phase == "preparing":
        due = (deadline - timedelta(days=7)) if deadline else None
        plan = ["ready", "ready", "working", "missing", "missing", "missing"]
        for n, key in enumerate(keys):
            status = plan[n] if n < len(plan) else ("working" if key == "budget" else "ready")
            owner = None if status == "missing" and n % 2 else user
            _item(tx, aid, key, owner, due, status)
        _review(tx, aid, keys[0], checklist[keys[0]], user, now, "approved", "Clear and specific.")
        return
    for key in keys:
        _item(tx, aid, key, user, None, "ready")
        _review(tx, aid, key, checklist[key], user, now - timedelta(days=2), "approved", "")
    final = {"by": str(user), "at": (now - timedelta(days=1)).isoformat(), "comment": "Ready."}
    tx.execute("UPDATE bids SET final_review = %s WHERE application_id = %s", (Jsonb(final), aid))
    add_event(tx, aid, "bid", user, action="final_review", comment="Ready.")
    if phase != "submitted":
        return
    submission = {
        "receipt": DEMO_RECEIPT,
        "portal": "Grants.gov",
        "submitted_at": (now - timedelta(hours=20)).isoformat(),
        "recorded_by": str(user),
        "recorded_at": (now - timedelta(hours=19)).isoformat(),
        "sent_by_hope": False,
    }
    tx.execute(
        "UPDATE bids SET submission = %s WHERE application_id = %s", (Jsonb(submission), aid)
    )
    add_event(tx, aid, "bid", user, action="submission", receipt=DEMO_RECEIPT)
    add_event(tx, aid, "stage", user, to="submitted", via="bid_receipt")


def _review(
    tx: Tx,
    aid: UUID,
    key: str,
    item: ChecklistItem,
    user: UUID,
    at: datetime,
    decision: str,
    comment: str,
) -> None:
    review = {
        "by": str(user),
        "at": at.isoformat(),
        "decision": decision,
        "comment": comment,
        "hash": item_hash(item),
    }
    tx.execute(
        "UPDATE bid_items SET review = %s WHERE application_id = %s AND item_key = %s",
        (Jsonb(review), aid, key),
    )


def seed() -> bool:
    """Seeds the three demo bids once; skips when any of their grants already has an
    application, or the demo grants or demo user are missing."""
    settings = get_settings()
    now = datetime.now().astimezone()
    with connect() as conn, tenant_tx(conn, settings.tenant_id) as tx:
        ids = {u: grant_id(tx, u) for u in BIDS}
        found = [i for i in ids.values() if i is not None]
        user = store.get_user_by_email(tx, DEMO_EMAIL)
        if user is None or len(found) < len(ids):
            return False
        tx.execute("SELECT 1 FROM applications WHERE grant_id = ANY(%s) LIMIT 1", (found,))
        if tx.fetchone() is not None:
            return False
        for url, gid in ids.items():
            assert gid is not None
            _seed_bid(tx, url, gid, user.user_id, now)
    return True
