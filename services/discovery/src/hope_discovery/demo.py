"""Demo seed for discovery, run by `hope-demo-seed` after the profile seed. Idempotent.

Runs the agent inline and offline (MockProvider + recorded pages), even when a key is set,
then dates the run 2 days back.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from uuid import UUID

from hope_core import store
from hope_core.money import Money
from hope_core.schemas.agency_profile import (
    AgencyProfile,
    ApprovalRule,
    Demographic,
    Financials,
    Legal,
    Mission,
    Program,
)
from hope_core.schemas.hitl import Gate
from hope_core.settings import get_settings
from hope_core.store import Tx

from hope_discovery import demo_grants, repo
from hope_discovery.agent import DiscoveryAgent
from hope_discovery.repo import DbRepo
from hope_discovery.runner import offline_tools

DEMO_REQUEST: tuple[list[str], str] = (["dental"], "Chelan County, WA")
SHIFT = timedelta(days=2)


def demo_profile() -> AgencyProfile:
    """Stand-in for H1's demo profile when its seed hasn't stored one; never written."""
    s = get_settings()
    return AgencyProfile(
        agency_id=s.agency_id,
        tenant_id=s.tenant_id,
        version=1,
        service_area=["Chelan County, WA", "Douglas County, WA"],
        legal=Legal(
            legal_name="Riverbend Community Health Alliance",
            ein="91-1234567",
            tax_status="501c3_public_charity",
            hq_city="Wenatchee",
            hq_state="WA",
        ),
        mission=Mission(
            mission_statement=(
                "Riverbend brings dental, primary and behavioral health care to rural and"
                " farmworker families in north central Washington."
            ),
            focus_areas=["rural health", "oral health", "community health workers"],
        ),
        financials=Financials(
            fiscal_year_end="06-30", annual_operating_budget=Money.from_decimal("3100000")
        ),
        programs=[
            Program(
                program_id="prog-dental",
                name="Mobile Dental Clinic",
                description=(
                    "Two mobile units provide cleanings, sealants and restorative care at"
                    " schools and farmworker housing."
                ),
                target_demographics=[
                    Demographic(population="rural children and farmworker families")
                ],
            ),
            Program(
                program_id="prog-chw",
                name="Community Health Workers",
                description="Bilingual community health workers connect families to care.",
            ),
        ],
        approval_hierarchy=[
            ApprovalRule(gate=Gate.GO_NO_GO, approver_roles=["executive_director"])
        ],
    )


class _DemoRepo(DbRepo):
    def __init__(self, fallback: AgencyProfile) -> None:
        self.fallback = fallback

    def load_profile(self) -> AgencyProfile | None:
        return super().load_profile() or self.fallback


def _demo_user(tx: Tx) -> UUID | None:
    tx.execute("SELECT user_id FROM users ORDER BY created_at LIMIT 1")
    row = tx.fetchone()
    return UUID(str(row["user_id"])) if row else None


def seed() -> UUID | None:
    """Adds the recorded real grants (`demo_grants`), then the offline run. Returns the new job
    id, or None when a discovery run already exists."""
    repo.with_tx(lambda tx: demo_grants.seed_grants(tx, datetime.now().astimezone().date()))

    def create(tx: Tx) -> UUID | None:
        repo.lock(tx)
        if store.list_jobs(tx, repo.KIND, 1):
            return None
        profile = store.get_profile(tx)
        user = _demo_user(tx)
        job = store.create_job(tx, repo.KIND, created_by=user)
        keywords, location = DEMO_REQUEST
        repo.insert_run(
            tx,
            job.job_id,
            keywords,
            location,
            profile.version if profile else None,
            user or UUID(int=0),
        )
        store.claim_job(tx, job.job_id, repo.KIND)
        new_id: UUID = job.job_id
        return new_id

    job_id = repo.with_tx(create)
    if job_id is None:
        return None
    gateway, web = offline_tools()
    result = DiscoveryAgent(_DemoRepo(demo_profile()), gateway, web).run(job_id)

    def finish(tx: Tx) -> None:
        store.finish_job(tx, job_id, result=result)
        repo.shift_back(tx, job_id, SHIFT)

    repo.with_tx(finish)
    return job_id
