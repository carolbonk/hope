"""Grant jargon in plain language, with where each explanation comes from.

Funders say "UEI", "SF-424A", "MTDC" or "letter of inquiry" and expect small nonprofits to know
what they mean. Code finds the terms on the funder's pages; each one is explained from this
vetted list (with an official source where one exists), the funder's own definition, or, last,
a model reading that staff are told to check. Code also says whether the profile already covers
the term and whether something takes weeks to get ready.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from typing import Literal

from hope_core.schemas.agency_profile import AgencyProfile
from pydantic import BaseModel

Owner = Literal["program", "finance", "director"]
Have = tuple[bool | None, str | None]

IRS = "https://www.irs.gov"
SAM = "https://sam.gov/content/entity-registration"
GRANTS_REG = "https://www.grants.gov/applicants/applicant-registration"
GRANTS_TERMS = "https://www.grants.gov/learn-grants/grant-terminology"
SF424 = "https://www.grants.gov/forms/forms-repository/sf-424-family"
ASSURANCES = "https://www.grants.gov/learn-grants/grant-policies/certifications-and-assurances"


def ecfr(section: str) -> str:
    return f"https://www.ecfr.gov/current/title-2/section-{section}"


@dataclass(frozen=True)
class Term:
    key: str
    label: str
    pattern: str  # case-sensitive; wrap phrases in (?i:...)
    plain: str
    owner: Owner
    url: str | None = None  # official explanation; None = Hope's own wording
    todo: str | None = None
    lead_days: int = 0  # how long getting it ready usually takes
    task: bool = False  # something the nonprofit must have or do, not just a word to know


TERMS: tuple[Term, ...] = (
    Term("ein", "EIN", r"\bEIN\b|(?i:employer identification number)|\bTIN\b",
         "Your organization's 9-digit federal tax ID number from the IRS.", "finance",
         f"{IRS}/businesses/small-businesses-self-employed/employer-identification-number",
         task=True),
    Term("uei", "UEI (Unique Entity ID)", r"\bUEI\b|(?i:unique entity (?:identifier|id))|\bDUNS\b",
         "A free 12-character ID for your organization issued by SAM.gov. It replaced the"
         " DUNS number. You can request just the ID without a full SAM registration.",
         "director", SAM, "Request it at SAM.gov.", 7, True),
    Term("sam", "SAM.gov registration",
         r"\bSAM\.gov\b|(?i:system for award management)|(?i:registered (?:in|with) SAM)\b",
         "The federal government's registry of organizations that can receive federal money."
         " Registration is free, must be renewed every year and must be active when you apply.",
         "director", SAM, "Register or renew at SAM.gov; it can take several weeks.", 30, True),
    Term("grants_gov", "Grants.gov account",
         r"(?i:grants\.gov (?:account|registration|workspace)|(?:register(?:ed)?|apply|submit)"
         r" (?:with|in|on|through|via) grants\.gov)",
         "The federal website where federal grant applications are submitted. Your organization"
         " needs an active SAM.gov registration and a Grants.gov account first.",
         "director", GRANTS_REG, "Create the account and link it to your UEI.", 7, True),
    Term("aor", "AOR (Authorized Organization Representative)",
         r"\bAOR\b|(?i:authori[sz]ed organi[sz]ation(?:al)? representative)",
         "The person allowed to submit and sign applications for your organization in"
         " Grants.gov, usually the executive director.",
         "director", GRANTS_TERMS, "Have your Grants.gov administrator give this person the"
         " AOR role.", 3, True),
    Term("login_gov", "Login.gov", r"(?i:login\.gov)",
         "The government sign-in used by SAM.gov and Grants.gov. Each person needs their own.",
         "director", "https://login.gov/", "Each person who signs in creates an account.", 1, True),
    Term("era", "eRA Commons", r"(?i:era commons)",
         "The NIH and HHS system used for some health grants. Your organization and the project"
         " lead each need an account.", "director",
         "https://www.era.nih.gov/register-accounts/understanding-era-commons-accounts.htm",
         "Register the organization, then the project lead.", 14, True),
    Term("sf424a", "SF-424A", r"\bSF[- ]?424A\b",
         "The federal budget form for non-construction projects: costs by category (personnel,"
         " fringe, travel, equipment, supplies, contractual, other, indirect) for each year.",
         "finance", SF424),
    Term("sf424b", "SF-424B", r"\bSF[- ]?424B\b",
         "Standard promises (assurances) every federal applicant signs.", "director", SF424),
    Term("sf424", "SF-424", r"\bSF[- ]?424(?![A-Z0-9])",
         "The standard federal cover form: who you are, what you're asking for, project dates"
         " and the signature of your authorized representative.", "director", SF424),
    Term("sflll", "SF-LLL", r"\bSF[- ]?LLL\b|(?i:disclosure of lobbying activities)",
         "A lobbying disclosure. You usually only file it if you paid someone to lobby for"
         " federal funds.", "director", SF424),
    Term("assurances", "Certifications and assurances", r"(?i:certifications and assurances)",
         "Legal promises you sign about following federal rules (civil rights, drug-free"
         " workplace, lobbying and others).", "director", ASSURANCES),
    Term("nofo", "NOFO", r"\bNOFO\b|(?i:notice of funding opportunity)|\bFOA\b"
         r"|(?i:funding opportunity announcement)",
         "The federal announcement for this grant: who can apply, what to send, the deadline and"
         " how applications are scored. Read the scoring section first.", "program", GRANTS_TERMS),
    Term("rfp", "RFP", r"\bRFPs?\b|(?i:request for proposals?)",
         "The funder's call for applications, with its rules and questions.", "program"),
    Term("rfa", "RFA", r"\bRFAs?\b|(?i:request for applications)",
         "The funder's call for applications, with its rules and questions.", "program"),
    Term("loi", "Letter of inquiry (LOI)", r"\bLOIs?\b|(?i:letters? of (?:inquiry|intent))",
         "A short first letter (often 1 to 3 pages) about your organization and project. The"
         " funder invites a full application only if it's interested.", "program"),
    Term("aln", "Assistance Listing (ALN / CFDA)", r"\bALN\b|\bCFDA\b|(?i:assistance listing)",
         "The number of the federal program this grant comes from, like 93.243.", "program",
         "https://sam.gov/content/assistance-listings"),
    Term("nicra", "NICRA", r"\bNICRA\b|(?i:negotiated indirect cost rate)",
         "An indirect-cost rate your organization negotiated with a federal agency. Most small"
         " nonprofits don't have one and can use the de minimis rate instead.", "finance",
         ecfr("200.414")),
    Term("de_minimis", "De minimis rate", r"(?i:de minimis)",
         "A flat indirect-cost rate you can charge without negotiating one: up to 15% of"
         " modified total direct costs (MTDC) under the federal rules.", "finance",
         ecfr("200.414")),
    Term("mtdc", "MTDC", r"\bMTDC\b|(?i:modified total direct costs?)",
         "The costs an indirect rate is applied to: salaries, fringe, materials, supplies,"
         " services, travel and the first $50,000 of each subaward. Equipment and rent are"
         " left out.", "finance", ecfr("200.1")),
    Term("indirect", "Indirect costs",
         r"(?i:indirect costs?|overhead|facilities and administrative)|\bF&A\b",
         "Shared costs not tied to one project, like rent, accounting, IT and leadership."
         " Funders often cap them; check this funder's limit.", "finance", ecfr("200.414")),
    Term("match", "Cost share / match",
         r"(?i:cost[- ]shar\w*|matching (?:funds|requirement|contribution)|\d+:\d+ match"
         r"|dollar[- ]for[- ]dollar)",
         "Money or donated value your organization must add from other sources, often a set"
         " ratio such as 1:1.", "finance", ecfr("200.306"),
         "Name where the match comes from and get it in writing.", 14, True),
    Term("in_kind", "In-kind", r"(?i:in-kind)",
         "Donated goods, space or volunteer time, counted at fair value instead of cash.",
         "finance", ecfr("200.306")),
    Term("budget_justification", "Budget justification",
         r"(?i:budget (?:justification|narrative))",
         "A written explanation of each budget line: what it pays for and how you calculated it.",
         "finance"),
    Term("fringe", "Fringe benefits", r"(?i:fringe(?: benefits?)?)",
         "Employer costs on top of salaries (payroll taxes, health insurance, retirement),"
         " usually shown as a percent of salary.", "finance", ecfr("200.431")),
    Term("fte", "FTE", r"\bFTEs?\b|(?i:full[- ]time equivalent)",
         "Staff time as a share of a full-time job: 0.5 FTE is half-time.", "finance"),
    Term("single_audit", "Single Audit", r"(?i:single audit)|\bA-133\b",
         "A special audit required in any year your organization spends $1,000,000 or more in"
         " federal awards.", "finance", ecfr("200.501")),
    Term("audit", "Audited financial statements",
         r"(?i:audited financial statements?|independent audit|financial audit)",
         "Financial statements checked by an outside CPA. Some funders accept a CPA review or"
         " your Form 990 instead if your budget is small; check this funder's rule.", "finance",
         todo="Attach your most recent audit.", lead_days=0, task=True),
    Term("form_990", "Form 990", r"\b990(?:-EZ|-N)?\b",
         "The yearly return nonprofits file with the IRS. It's public, and funders use it to"
         " check your finances.", "finance", f"{IRS}/forms-pubs/about-form-990",
         "Attach the most recent filed return.", task=True),
    Term("determination_letter", "IRS determination letter",
         r"(?i:determination letter|proof of (?:tax[- ]exempt|501\s?\(c\)\s?\(3\)) status)",
         "The IRS letter confirming your organization is tax-exempt under 501(c)(3).", "director",
         f"{IRS}/charities-non-profits/charitable-organizations/exemption-requirements-501c3-organizations",
         "Attach the IRS letter.", task=True),
    Term("w9", "W-9", r"\bW-?9\b",
         "An IRS form with your legal name, address and EIN, so the funder can pay you.",
         "finance", f"{IRS}/forms-pubs/about-form-w-9", task=True),
    Term("good_standing", "Certificate of good standing", r"(?i:good standing)",
         "A record from your state that your nonprofit is active and up to date with its"
         " filings. You get it from your Secretary of State.", "director",
         todo="Request it from your Secretary of State.", lead_days=5, task=True),
    Term("fiscal_sponsor", "Fiscal sponsor", r"(?i:fiscal(?:ly)? sponsor\w*)",
         "An established nonprofit that receives and manages grant money for a project that"
         " isn't its own 501(c)(3).", "director"),
    Term("board_list", "Board list", r"(?i:board (?:list|roster|of directors list)|list of"
         r" (?:board members|directors))",
         "The names, and often the jobs or affiliations, of your board members.", "director",
         task=True),
    Term("letters_support", "Letters of support",
         r"(?i:letters? of (?:support|commitment|endorsement))",
         "Letters from partners or community members backing the project. Collecting them takes"
         " time.", "director", todo="Ask partners now and give them a draft to edit.",
         lead_days=14, task=True),
    Term("mou", "MOU", r"\bMOUs?\b|(?i:memorand(?:um|a) of (?:understanding|agreement))",
         "A signed agreement with a partner that says who does what.", "director",
         todo="Agree on roles with each partner and get it signed.", lead_days=21, task=True),
    Term("subaward", "Subaward", r"(?i:sub-?awards?|sub-?recipients?|sub-?grants?)",
         "Passing part of the grant to another organization to do part of the work. You stay"
         " responsible for overseeing it.", "finance", ecfr("200.331")),
    Term("logic_model", "Logic model", r"(?i:logic model)",
         "A one-page chart linking your resources to activities, outputs and outcomes.",
         "program"),
    Term("smart", "SMART objectives", r"\bSMART\b(?= (?:goals?|objectives?))",
         "Objectives that are Specific, Measurable, Achievable, Relevant and Time-bound, e.g."
         " '150 adults get a screening by June 2027'.", "program"),
    Term("outputs", "Outputs vs outcomes", r"(?i:\boutputs\b)",
         "Outputs are what you deliver (200 visits). Outcomes are the change that results (fewer"
         " ER visits).", "program"),
    Term("theory_of_change", "Theory of change", r"(?i:theory of change)",
         "Your explanation of why your activities lead to the change you want.", "program"),
    Term("evaluation_plan", "Evaluation plan", r"(?i:evaluation plan)",
         "How you'll tell whether the project worked: what data, when, and who collects it.",
         "program"),
    Term("sustainability", "Sustainability plan", r"(?i:sustainability plan)",
         "How the work continues after this grant ends: other funding, earned revenue or"
         " partners.", "program"),
    Term("key_personnel", "Key personnel", r"(?i:key personnel|biographical sketch|biosketch)",
         "Short bios or résumés of the people leading the project.", "program",
         todo="Collect a short bio for each project lead.", lead_days=3, task=True),
    Term("period", "Period of performance", r"(?i:period of performance|project period|budget"
         r" period)",
         "The dates during which grant money may be spent.", "program", ecfr("200.1")),
    Term("reimbursement", "Reimbursement basis",
         r"(?i:reimbursement basis|cost[- ]reimbursement|on a reimbursement)",
         "You spend the money first and the funder pays you back later, so you need cash on"
         " hand to cover costs in the meantime.", "finance", ecfr("200.305")),
    Term("gos", "General operating support", r"(?i:general operating support|unrestricted"
         r" (?:funds|support|grants?))",
         "Money you can use for any part of your mission, not just one project.", "finance"),
    Term("uniform_guidance", "Uniform Guidance (2 CFR 200)",
         r"(?i:uniform guidance)|\b2 CFR(?: Part)? 200\b",
         "The federal rules for how grant money may be spent, tracked and audited.", "finance",
         "https://www.ecfr.gov/current/title-2/subtitle-A/chapter-II/part-200"),
    Term("cdbg", "CDBG", r"\bCDBG\b|(?i:community development block grant)",
         "Federal housing and community development money (from HUD) that cities and counties"
         " pass on to local nonprofits. It comes with federal rules on who may benefit and on"
         " reporting.", "program"),
    Term("fiscal_year", "Fiscal year (FY)", r"\bFY ?\d{2,4}\b|(?i:fiscal year)",
         "Your organization's 12-month accounting year, which may not match the calendar year."
         " 'FY26' means the fiscal year ending in 2026.", "finance"),
    Term("dei", "DEI", r"\bDEI\b|(?i:diversity, equity,? (?:and|&) inclusion)",
         "Diversity, equity and inclusion: how your organization and project include and serve"
         " people of different backgrounds. Funders often ask for board and staff demographics.",
         "director"),
    Term("coi_policy", "Conflict of interest policy", r"(?i:conflict[s]? of interest)",
         "A board-approved policy on how board members and staff handle personal interests that"
         " could affect decisions.", "director", todo="Attach the board-approved policy.",
         task=True),
    Term("debarment", "Debarment and suspension", r"(?i:debar\w*)",
         "A promise that your organization isn't barred from receiving federal money. SAM.gov"
         " records this.", "director", ASSURANCES),
)  # fmt: skip

BY_KEY = {t.key: t for t in TERMS}
_COMPILED = [(t, re.compile(t.pattern)) for t in TERMS]
_SENTENCE = re.compile(r"[^.!?\n]*(?:[.!?]|$)")


def glossary_term(name: str) -> Term | None:
    """The vetted term a name refers to ('UEI', 'Unique Entity ID'), if any."""
    return next((t for t, rx in _COMPILED if rx.search(name)), None)


class TermUse(BaseModel):
    """A term the funder uses, with their sentence. `meaning` is set only when the term isn't
    in the glossary: the funder's own definition (`source="funder"`) or a model reading."""

    key: str | None = None
    term: str
    quote: str
    url: str
    source: Literal["glossary", "funder", "ai"] = "glossary"
    meaning: str | None = None


def find_terms(text: str, url: str) -> list[TermUse]:
    """Every glossary term on a page, once, with the first sentence that uses it."""
    out: list[TermUse] = []
    for term, rx in _COMPILED:
        m = rx.search(text)
        if m is None:
            continue
        sentence = next(
            (s for s in _SENTENCE.finditer(text) if s.start() <= m.start() < s.end()), None
        )
        quote = " ".join((sentence[0] if sentence else m[0]).split())[:300]
        out.append(TermUse(key=term.key, term=m[0], quote=quote or m[0], url=url))
    return out


# --- what the nonprofit already has -----------------------------------------------------------


def _sam(p: AgencyProfile, deadline: date | None) -> Have:
    reg = p.legal.sam_registration
    if reg is None:
        return None, None
    if reg.status == "active":
        if reg.expires_on and deadline and reg.expires_on < deadline:
            return False, f"Expires {reg.expires_on.isoformat()}, before the deadline: renew it."
        expiry = f", expires {reg.expires_on.isoformat()}" if reg.expires_on else ""
        return True, f"Active in your profile{expiry}."
    if reg.status == "pending":
        return None, "Pending in your profile."
    return False, f"Your profile says SAM registration is {reg.status}."


HAVE: dict[str, Callable[[AgencyProfile, date | None], Have]] = {
    "ein": lambda p, _d: (True, f"EIN {p.legal.ein} from your profile."),
    "uei": lambda p, _d: (
        (True, f"UEI {p.legal.uei} from your profile.")
        if p.legal.uei
        else (False, "No UEI in your profile.")
    ),
    "sam": _sam,
    "fiscal_sponsor": lambda p, _d: (
        (True, "Your profile names a fiscal sponsor.")
        if p.legal.fiscal_sponsor_id
        else (None, None)
    ),
    "theory_of_change": lambda p, _d: (
        (True, "Your profile has a theory of change.")
        if p.mission.theory_of_change
        else (None, None)
    ),
    "determination_letter": lambda p, _d: (
        (None, "Your profile says 501(c)(3); attach the letter.")
        if p.legal.tax_status.startswith("501c3")
        else (False, "Your profile doesn't list 501(c)(3) status.")
    ),
}

Status = Literal["have", "check", "action_needed", "at_risk", "info"]


class TermExplained(BaseModel):
    """One funder term for staff: the funder's words, what they mean, and who says so."""

    key: str | None
    term: str
    plain: str
    explained_by: Literal["official", "hope", "funder", "ai"]
    source_url: str | None = None
    quote: str
    url: str
    owner: Owner | None = None
    todo: str | None = None
    lead_days: int = 0
    status: Status = "info"
    detail: str | None = None


def explain(
    uses: list[TermUse], profile: AgencyProfile | None, deadline: date | None, today: date
) -> list[TermExplained]:
    out: list[TermExplained] = []
    for use in uses:
        term = BY_KEY.get(use.key) if use.key else None
        if term is None:
            out.append(
                TermExplained(
                    key=None,
                    term=use.term,
                    plain=use.meaning or "",
                    explained_by="funder" if use.source == "funder" else "ai",
                    source_url=use.url if use.source == "funder" else None,
                    quote=use.quote,
                    url=use.url,
                    detail=None
                    if use.source == "funder"
                    else "Hope's reading: check it with the funder.",
                )
            )
            continue
        status: Status = "info"
        detail = None
        if term.task:
            has, detail = (
                HAVE[term.key](profile, deadline)
                if profile and term.key in HAVE
                else (
                    None,
                    None,
                )
            )
            status = "have" if has else "check" if has is None else "action_needed"
            days_left = (deadline - today).days if deadline else None
            if (
                status != "have"
                and term.lead_days
                and days_left is not None
                and (days_left < term.lead_days)
            ):
                status = "at_risk"
                detail = (detail + " " if detail else "") + (
                    f"Usually takes about {term.lead_days} days; {max(days_left, 0)} left."
                )
        out.append(
            TermExplained(
                key=term.key,
                term=term.label,
                plain=term.plain,
                explained_by="official" if term.url else "hope",
                source_url=term.url,
                quote=use.quote,
                url=use.url,
                owner=term.owner,
                todo=term.todo,
                lead_days=term.lead_days,
                status=status,
                detail=detail,
            )
        )
    order = {"at_risk": 0, "action_needed": 1, "check": 2, "have": 3, "info": 4}
    return sorted(out, key=lambda t: (order[t.status], -t.lead_days))
