"""Real open grants for the demo deck, recorded on 2026-11-08 from Grants.gov and cfncw.org.

Quotes are the sources' own words (Grants.gov notices as `grantsgov.render` lays them out). Code
parses the amount and deadline from those quotes, as discovery does. Fit scores and reasons are
hand-written for the demo agency. Amounts and dates go stale; check the linked page.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

from hope_core import store
from hope_core.schemas import GrantCandidate
from hope_core.schemas.hackathon import Citation
from hope_core.store import Tx

from hope_discovery import repo
from hope_discovery.parse import parse_amount, parse_deadline

RECORDED = datetime(2026, 11, 8, 12, tzinfo=UTC)
GG = "https://www.grants.gov/search-results-detail/"
MENTORING = f"{GG}364058"
YOUTH_TREATMENT = f"{GG}364040"
OPIOID_YOUTH = f"{GG}364057"
TITLE_X = f"{GG}361754"
WISH = f"{GG}363546"
SMALL_PROVIDER_QI = f"{GG}362831"
NCW_YOUTH = "https://cfncw.org/ncwfoundationforyouthgrant/"
WATERVILLE = "https://cfncw.org/watervillecommunityfundgrant/"

GRANTS: list[dict[str, Any]] = [
    {
        "url": MENTORING,
        "title": "OJJDP FY 2026 Mentoring for Youth Impacted by Opioids and Other Substance Use",
        "funder": "Office of Juvenile Justice and Delinquency Prevention",
        "summary": "Funds mentoring for youth who use substances, are at risk, or have family"
        " members with substance use [c1]. Open to 501(c)(3) nonprofits [c2].",
        "amount_text": "Awards: up to $2,000,000 per award.",
        "deadline_text": "Deadline: Applications due November 16, 2026.",
        "eligibility_summary": "Nonprofits with or without 501(c)(3) status, tribes, states,"
        " counties, cities, school districts and colleges.",
        "fit_score": 74,
        "fit_reasons": [
            "Community health workers already reach farmworker youth and families.",
            "Behavioral health support is part of Riverbend's mission.",
        ],
        "concerns": ["Due in about a week.", "Riverbend has no formal mentoring program yet."],
        "quotes": [
            "This opportunity supports the implementation and delivery of high-quality mentoring"
            " services for youth who are currently using or dependent on substances, as well as"
            " youth at risk of substance use or who have close family members experiencing"
            " substance use or dependency.",
            "Nonprofits having a 501(c)(3) status with the IRS, other than institutions of higher"
            " education",
        ],
    },
    {
        "url": YOUTH_TREATMENT,
        "title": "OJJDP FY 2026 Expanding Youth Access to Community-Based Treatment",
        "funder": "Office of Juvenile Justice and Delinquency Prevention",
        "summary": "Funds community-based treatment for youth with substance use or co-occurring"
        " mental health disorders [c1].",
        "amount_text": "Awards: up to $650,000 per award.",
        "deadline_text": "Deadline: Applications due November 16, 2026.",
        "eligibility_summary": "Nonprofits, tribes, states, counties and cities.",
        "fit_score": 69,
        "fit_reasons": ["Riverbend's clinics already provide mental health support."],
        "concerns": ["Needs a partnership with the juvenile justice system."],
        "quotes": [
            "This opportunity will fund community-based treatment programs serving youth with"
            " substance use disorders (SUD) and co-occurring mental health and substance use"
            " disorders (MHSUD).",
        ],
    },
    {
        "url": OPIOID_YOUTH,
        "title": "OJJDP FY 2026 Opioid Affected Youth Initiative",
        "funder": "Office of Juvenile Justice and Delinquency Prevention",
        "summary": "Supports prevention, intervention and treatment for children, youth and"
        " families affected by opioid and other substance use disorders [c1].",
        "amount_text": "Awards: up to $750,000 per award.",
        "deadline_text": "Deadline: Applications due November 16, 2026.",
        "eligibility_summary": "Nonprofits, tribes, states, counties and cities.",
        "fit_score": 58,
        "fit_reasons": ["Families served by the community health workers are in scope."],
        "concerns": ["Expects collaboration with law enforcement and justice agencies."],
        "quotes": [
            "This NOFO supports states, localities, Tribal jurisdictions, and non-profit"
            " organizations in addressing violent crime and reducing overdose deaths through"
            " prevention, intervention, and treatment strategies to support children, youth, and"
            " families affected by opioid, stimulant, and other substance use disorders.",
        ],
    },
    {
        "url": TITLE_X,
        "title": "Title X Family Planning Services Grants",
        "funder": "Office of the Assistant Secretary for Health",
        "summary": "FY 2027 grants for Title X family planning services across the U.S. [c1].",
        "amount_text": "Awards: $200,000 to $22,000,000 per award.",
        "deadline_text": "Deadline: Applications due January 11, 2027.",
        "eligibility_summary": "Nonprofits, states, tribes, counties, cities and colleges.",
        "fit_score": 81,
        "fit_reasons": [
            "Preventive care for rural families regardless of ability to pay.",
            "Bilingual staff already serve Spanish-speaking farmworker families.",
        ],
        "concerns": ["Large federal reporting load."],
        "quotes": [
            "The Office of Population Affairs (OPA) announces the anticipated availability of"
            " funds for Fiscal Year (FY) 2027 grants under the authority of Title X of the Public"
            " Health Service Act",
        ],
    },
    {
        "url": WISH,
        "title": "Women's Initiative for Screening and Health (WISH)",
        "funder": "Health Resources and Services Administration",
        "summary": "Improves women's access to preventive health services through a"
        " coalition of providers, academic institutions and patient groups [c1].",
        "amount_text": "Awards: up to $1,000,000 per award.",
        "deadline_text": "Deadline: Applications due January 8, 2027.",
        "eligibility_summary": "Nonprofits, colleges, states, tribes, counties and cities.",
        "fit_score": 62,
        "fit_reasons": ["Preventive screening is central to Riverbend's clinics."],
        "concerns": ["One national award; suits a national coalition lead better."],
        "quotes": [
            "The purpose of Women's Initiative for Screening and Health (WISH) is to improve"
            " women\u2019s health across the lifespan by increasing access to and availability of"
            " preventive health services.",
        ],
    },
    {
        "url": SMALL_PROVIDER_QI,
        "title": "Small Health Care Provider Quality Improvement Program",
        "funder": "Health Resources and Services Administration",
        "summary": "Builds quality improvement capacity in small rural hospitals and clinics,"
        " with a focus on chronic disease outcomes [c1].",
        "amount_text": "Awards: up to $250,000 per award.",
        "deadline_text": "Deadline: Applications due August 6, 2026.",
        "eligibility_summary": "501(c)(3) nonprofits, tribal organizations, states, counties,"
        " cities and public colleges.",
        "fit_score": 84,
        "fit_reasons": ["Riverbend runs small rural clinics in Chelan and Douglas counties."],
        "concerns": ["Closed on August 6, 2026; watch for the next round."],
        "quotes": [
            "The purpose of the Small Health Care Provider Quality Improvement Program is to"
            " strengthen the quality improvement culture in small rural healthcare facilities by"
            " building capacity to effectively collect and use clinical data",
        ],
        "found": datetime(2026, 7, 14, 16, tzinfo=UTC),
        "status": "saved",
    },
    {
        "url": NCW_YOUTH,
        "title": "NCW Foundation for Youth Grant",
        "funder": "Community Foundation of North Central Washington",
        "summary": "Small grants for programs that directly benefit youth in Chelan and Douglas"
        " counties [c1].",
        "amount_text": "Up to $1,000 can be requested for one or more projects/programs per"
        " organization",
        "deadline_text": "Applications are accepted year-round, with review periods in July,"
        " November, and March.",
        "eligibility_summary": "501(c)(3) nonprofits serving Chelan County, WA or Douglas"
        " County, WA with annual operating expenses under $250,000.",
        "fit_score": 22,
        "fit_reasons": ["Serves Riverbend's two counties."],
        "concerns": ["Riverbend's $3.1M budget is over the $250,000 expense limit."],
        "quotes": [
            "The NCW Foundation for Youth Grant was established in 2017 to provide funding for"
            " programs that directly benefit youth in Chelan and Douglas counties.",
        ],
    },
    {
        "url": WATERVILLE,
        "title": "Waterville Community Fund Grant",
        "funder": "Community Foundation of North Central Washington",
        "summary": "Funds programs that meet the needs of the Waterville community, including"
        " health and human services [c1].",
        "amount_text": None,
        "deadline_text": "Application Deadline: December 1",
        "eligibility_summary": "501(c)(3) nonprofits or agencies whose program serves"
        " Waterville, in Douglas County, WA.",
        "fit_score": 63,
        "fit_reasons": ["Waterville is in Douglas County, inside Riverbend's service area."],
        "concerns": ["The page gives no award size or year for the deadline."],
        "quotes": [
            "The Waterville Community Fund provides grant funding for innovative programs that"
            " help to meet the needs of the Waterville community and its citizens.",
        ],
    },
]


def grant_id(tx: Tx, url: str) -> UUID | None:
    """This tenant's grant for `url` (ids are per tenant, so they are looked up, not derived)."""
    tx.execute("SELECT grant_id FROM grant_candidates WHERE url = %s", (url,))
    row = tx.fetchone()
    return UUID(str(row["grant_id"])) if row else None


def candidate(spec: dict[str, Any], today: date, found: datetime) -> GrantCandidate:
    amount = parse_amount(spec["amount_text"])
    deadline = parse_deadline(spec["deadline_text"], today)
    # A deadline that was still ahead when the notice was recorded is kept once it has passed.
    found_on = spec.get("found", RECORDED).date()
    due = deadline.date or next(
        (d for d in sorted(deadline.all_dates) if found_on <= d < today), None
    )
    return GrantCandidate(
        grant_id=uuid4(),
        title=spec["title"],
        funder=spec["funder"],
        url=spec["url"],
        summary=spec["summary"],
        amount_text=spec["amount_text"],
        amount_max=amount.max if amount else None,
        deadline_text=spec["deadline_text"],
        deadline=due,
        eligibility_summary=spec["eligibility_summary"],
        fit_score=spec["fit_score"],
        fit_reasons=spec["fit_reasons"],
        concerns=spec["concerns"],
        citations=[
            Citation(
                citation_id=f"c{n}",
                kind="web",
                url=spec["url"],
                title=spec["title"],
                quote=q,
                retrieved_at=RECORDED,
            )
            for n, q in enumerate(spec["quotes"], start=1)
        ],
        discovered_at=spec.get("found", found),
        status=spec.get("status", "new"),
    )


def seed_grants(tx: Tx, today: date) -> int:
    """Adds each recorded grant once (by URL); returns how many were new."""
    now = datetime.now(UTC)
    added = 0
    for n, spec in enumerate(GRANTS):
        if repo.url_exists(tx, spec["url"]):
            continue
        found = now - timedelta(days=1, hours=3 * n)
        store.upsert_candidate(tx, candidate(spec, today, found))
        added += 1
    return added
