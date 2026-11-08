"""H6: each grant's own rules, checked against the nonprofit's profile by code.

The reader copies the funder's eligibility, budget and conditional sentences word for word;
this module decides, from the profile and the request amount, whether each one is met, not met,
applies, doesn't apply, or needs a person to check. Nothing here calls a model."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Callable
from datetime import date
from typing import Literal

from hope_core.money import Money
from hope_core.schemas.agency_profile import AgencyProfile
from pydantic import BaseModel

from hope_discovery.glossary import Owner
from hope_discovery.parse import parse_amount
from hope_discovery.requirements import Requirements, Sourced

RuleKind = Literal["eligibility", "budget", "conditional"]
RuleStatus = Literal["met", "not_met", "unknown", "applies", "not_applicable"]


class RuleCheck(BaseModel):
    key: str
    kind: RuleKind
    label: str
    status: RuleStatus
    reason: str
    quote: str
    url: str
    owner: Owner
    todo: str | None = None
    confirmed_by_staff: bool = False


def rule_key(kind: str, quote: str) -> str:
    norm = re.sub(r"[^a-z0-9 ]", "", " ".join(quote.lower().split()))
    return f"rule:{hashlib.sha256(f'{kind}:{norm}'.encode()).hexdigest()[:12]}"


def usd(minor: int) -> str:
    return f"${minor / 100:,.0f}"


Result = tuple[RuleStatus, str, str | None]  # status, reason, todo

STATES = {
    "alabama": "AL", "alaska": "AK", "arizona": "AZ", "arkansas": "AR", "california": "CA",
    "colorado": "CO", "connecticut": "CT", "delaware": "DE", "florida": "FL", "georgia": "GA",
    "hawaii": "HI", "idaho": "ID", "illinois": "IL", "indiana": "IN", "iowa": "IA",
    "kansas": "KS", "kentucky": "KY", "louisiana": "LA", "maine": "ME", "maryland": "MD",
    "massachusetts": "MA", "michigan": "MI", "minnesota": "MN", "mississippi": "MS",
    "missouri": "MO", "montana": "MT", "nebraska": "NE", "nevada": "NV", "new hampshire": "NH",
    "new jersey": "NJ", "new mexico": "NM", "new york": "NY", "north carolina": "NC",
    "north dakota": "ND", "ohio": "OH", "oklahoma": "OK", "oregon": "OR", "pennsylvania": "PA",
    "rhode island": "RI", "south carolina": "SC", "south dakota": "SD", "tennessee": "TN",
    "texas": "TX", "utah": "UT", "vermont": "VT", "virginia": "VA", "washington": "WA",
    "west virginia": "WV", "wisconsin": "WI", "wyoming": "WY", "puerto rico": "PR",
}  # fmt: skip
_STATE_RX = re.compile(r"\b(?:State of )?(" + "|".join(s.title() for s in STATES) + r")\b")
_COUNTY_RX = re.compile(
    r"\b((?:[A-Z][a-z]+ ){0,2}[A-Z][a-z]+(?:,? (?:and|or) [A-Z][a-z]+)*) Count(?:y|ies)\b"
)
_PLACE_ASK = re.compile(
    r"located|based|serv(?:e|es|ing)|resid|headquarter|operat(?:e|ing) in", re.I
)
_ABOVE = r"(?:more than|over|exceed(?:s|ing)?|above|greater than|at least|minimum of|of at least)"
_BELOW = (
    r"(?:less than|under|below|no more than|not (?:to )?exceed(?:ing)?|up to|maximum of|or less)"
)


def _amount_bound(text: str, subject: str) -> tuple[str, int] | None:
    """('above'|'below', minor) for '<subject> ... more than $X' style sentences."""
    for direction, words in (("above", _ABOVE), ("below", _BELOW)):
        m = re.search(
            rf"(?:{subject})[^.;]{{0,60}}?{words}\s*(\$[\d,]+(?:\.\d+)?(?:\s*(?:k|m|million|thousand)\b)?)",
            text,
            re.I,
        )
        if m and (amount := parse_amount(m.group(1))) and amount.max:
            return direction, amount.max.amount_minor
    return None


def _profile_places(p: AgencyProfile) -> str:
    bits = [*p.service_area, p.legal.hq_city or "", p.legal.hq_state or ""]
    for prog in p.programs:
        bits += prog.geography
    return " | ".join(bits).lower()


def _in_place(name: str, places: str) -> bool:
    abbr = STATES.get(name.lower())
    return name.lower() in places or bool(abbr and re.search(rf"\b{abbr.lower()}\b", places))


# --- eligibility --------------------------------------------------------------------------------


def _tax(p: AgencyProfile, q: str, _d: date | None) -> Result:
    status = p.legal.tax_status
    if status.startswith("501c3"):
        return "met", "Your profile says you're a 501(c)(3).", None
    if status == "fiscally_sponsored" or p.legal.fiscal_sponsor_id:
        if re.search(r"fiscal(?:ly)? spons", q, re.I):
            return "met", "You apply through a fiscal sponsor, which this funder accepts.", None
        return (
            "unknown",
            "You apply through a fiscal sponsor; the funder doesn't say it accepts that.",
            "Ask the funder whether a fiscally sponsored project can apply.",
        )
    if status in ("government", "tribal") and re.search(r"government|tribal|public agenc", q, re.I):
        return "met", "Government and tribal applicants are listed.", None
    return "not_met", f"Your profile lists your tax status as {status.replace('_', ' ')}.", None


def _sam(p: AgencyProfile, _q: str, deadline: date | None) -> Result:
    reg = p.legal.sam_registration
    if reg is None:
        return (
            "unknown",
            "Your profile doesn't record a SAM.gov registration.",
            "Check your registration at SAM.gov; a new one can take several weeks.",
        )
    if reg.status != "active":
        return "not_met", f"Your SAM.gov registration is {reg.status}.", "Renew it at SAM.gov."
    if reg.expires_on and deadline and reg.expires_on < deadline:
        return (
            "not_met",
            f"Your SAM.gov registration expires {reg.expires_on:%b %-d, %Y}, before the deadline.",
            "Renew it at SAM.gov before you apply.",
        )
    return "met", "Your SAM.gov registration is active.", None


def _uei(p: AgencyProfile, _q: str, _d: date | None) -> Result:
    if p.legal.uei:
        return "met", f"UEI {p.legal.uei} is in your profile.", None
    return (
        "unknown",
        "Your profile doesn't record a UEI.",
        "Find your UEI at SAM.gov, or request one (it's free).",
    )


def _place(p: AgencyProfile, q: str, _d: date | None) -> Result:
    places = _profile_places(p)
    states = sorted({m.group(1) for m in _STATE_RX.finditer(q)})
    counties = [m.group(1) for m in _COUNTY_RX.finditer(q)]
    county_names = [c for group in counties for c in re.split(r",? (?:and|or) |, ", group)]
    if county_names:
        if any(c.lower() in places for c in county_names):
            return "met", "Your service area includes the counties named.", None
        return (
            "unknown",
            f"This grant names {', '.join(county_names)} County; your profile lists "
            f"{', '.join(p.service_area) or 'no service area'}.",
            "Confirm you serve the area the funder names.",
        )
    if states:
        if any(_in_place(s, places) for s in states):
            return "met", f"You're in or serve {', '.join(states)}.", None
        return (
            "not_met",
            f"This grant is for {', '.join(states)}; your profile lists "
            f"{', '.join(p.service_area) or p.legal.hq_state or 'no service area'}.",
            None,
        )
    return "unknown", "Hope couldn't tell which area this covers.", "Confirm you serve this area."


def _budget_size(p: AgencyProfile, q: str, _d: date | None) -> Result:
    ours = p.financials.annual_operating_budget.amount_minor
    bound = _amount_bound(q, r"budget")
    if bound is None:
        return "unknown", "Hope couldn't read the budget limit.", "Check the budget size rule."
    direction, limit = bound
    ok = ours > limit if direction == "above" else ours <= limit
    word = "over" if direction == "above" else "at most"
    reason = f"Your annual budget is {usd(ours)}; the funder wants {word} {usd(limit)}."
    return ("met" if ok else "not_met"), reason, None


def _years(_p: AgencyProfile, _q: str, _d: date | None) -> Result:
    return (
        "unknown",
        "Your profile doesn't record when you were founded.",
        "Confirm how many years you've been operating.",
    )


EligibilityCheck = Callable[[AgencyProfile, str, date | None], Result]
_ELIGIBILITY: list[tuple[str, re.Pattern[str], EligibilityCheck]] = [
    ("501(c)(3) status", re.compile(r"501\s*\(?c\)?\s*\(?3\)?|tax[- ]exempt|non-?profit", re.I),
     _tax),
    ("SAM.gov registration", re.compile(r"sam\.gov|system for award management", re.I), _sam),
    ("UEI", re.compile(r"\bUEI\b|unique entity id", re.I), _uei),
    ("Annual budget", re.compile(r"(?:annual|operating|organizational) budget", re.I),
     _budget_size),
    ("Years operating",
     re.compile(r"\byears?\b[^.]{0,40}(?:operat|existence|incorporat|establish|founded)", re.I),
     _years),
]  # fmt: skip
_RANK: dict[RuleStatus, int] = {
    "not_met": 0,
    "unknown": 1,
    "applies": 2,
    "not_applicable": 3,
    "met": 4,
}


def check_eligibility(s: Sourced, p: AgencyProfile, deadline: date | None) -> RuleCheck:
    results = [
        (label, fn(p, s.text, deadline)) for label, rx, fn in _ELIGIBILITY if rx.search(s.text)
    ]
    if _PLACE_ASK.search(s.text) and (_STATE_RX.search(s.text) or _COUNTY_RX.search(s.text)):
        results.append(("Location", _place(p, s.text, deadline)))
    if not results:
        return RuleCheck(
            key=rule_key("eligibility", s.text),
            kind="eligibility",
            label="Who can apply",
            status="unknown",
            reason="Hope can't check this one from your profile.",
            quote=s.text,
            url=s.url,
            owner="director",
            todo="Confirm you meet this.",
        )
    worst = min(results, key=lambda r: _RANK[r[1][0]])
    status = worst[1][0]
    todos = [r[1][2] for r in results if r[1][2] and r[1][0] != "met"]
    return RuleCheck(
        key=rule_key("eligibility", s.text),
        kind="eligibility",
        label=", ".join(label for label, _ in results),
        status=status,
        reason=" ".join(r[1][1] for r in results),
        quote=s.text,
        url=s.url,
        owner="director",
        todo=" ".join(todos) or None,
    )


# --- budget -------------------------------------------------------------------------------------


def _pct(text: str) -> float | None:
    if re.search(r"dollar[- ]for[- ]dollar|\b1\s*:\s*1\b|one[- ]to[- ]one", text, re.I):
        return 100.0
    m = re.search(r"(\d+(?:\.\d+)?)\s*(?:%|percent)", text, re.I)
    return float(m.group(1)) if m else None


def check_budget(req: Requirements, p: AgencyProfile | None, ask: Money | None) -> list[RuleCheck]:
    b, out = req.budget, []
    status: RuleStatus
    if b.max_request:
        if b.max_request_amount is None:
            status, reason = "unknown", "Hope couldn't read the maximum amount."
        elif ask is None:
            status, reason = (
                "unknown",
                f"The most you can request is {usd(b.max_request_amount.amount_minor)}.",
            )
        elif ask.amount_minor <= b.max_request_amount.amount_minor:
            status, reason = (
                "met",
                (
                    f"Your request of {usd(ask.amount_minor)} is within the "
                    f"{usd(b.max_request_amount.amount_minor)} maximum."
                ),
            )
        else:
            status, reason = (
                "not_met",
                (
                    f"Your request of {usd(ask.amount_minor)} is over the "
                    f"{usd(b.max_request_amount.amount_minor)} maximum."
                ),
            )
        out.append(
            RuleCheck(
                key=rule_key("budget", b.max_request.text),
                kind="budget",
                label="Maximum request",
                status=status,
                reason=reason,
                quote=b.max_request.text,
                url=b.max_request.url,
                owner="finance",
                todo=None
                if status == "met"
                else (
                    "Lower your request to the maximum."
                    if status == "not_met"
                    else "Set how much you're requesting."
                ),
            )
        )
    if b.match_rule:
        out.append(_match(b.match_rule, p, ask))
    if b.indirect_rule:
        out.append(_indirect(b.indirect_rule, p))
    return out


def _match(s: Sourced, p: AgencyProfile | None, ask: Money | None) -> RuleCheck:
    def rule(status: RuleStatus, reason: str, todo: str | None = None) -> RuleCheck:
        return RuleCheck(
            key=rule_key("budget", s.text), kind="budget", label="Match / cost share",
            status=status, reason=reason, quote=s.text, url=s.url, owner="finance", todo=todo,
        )  # fmt: skip

    if re.search(
        r"\bno (?:cash )?match|match(?:ing)? (?:is )?not required|not require[sd]? (?:a )?match",
        s.text,
        re.I,
    ):
        return rule("met", "No match is required.")
    pct = _pct(s.text)
    if pct is None:
        return rule(
            "unknown",
            "Hope couldn't read how much match is required.",
            "Work out the match the funder requires.",
        )
    if ask is None:
        return rule(
            "unknown",
            f"You need a {pct:g}% match; set your request to work out the amount.",
            "Set how much you're requesting.",
        )
    need = round(ask.amount_minor * pct / 100)
    todo = f"Line up {usd(need)} in match (cash or in-kind) and document where it comes from."
    have = p.capacity.cost_share_capacity if p and p.capacity else None
    if have is None:
        return rule("unknown", f"A {pct:g}% match on {usd(ask.amount_minor)} is {usd(need)}.", todo)
    if have.amount_minor >= need:
        return rule(
            "met",
            f"A {pct:g}% match is {usd(need)}; your profile says you can commit up to"
            f" {usd(have.amount_minor)}.",
            todo,
        )
    return rule(
        "not_met",
        f"A {pct:g}% match is {usd(need)}; your profile says you can commit"
        f" {usd(have.amount_minor)}.",
        todo,
    )


def _indirect(s: Sourced, p: AgencyProfile | None) -> RuleCheck:
    def rule(status: RuleStatus, reason: str, todo: str | None = None) -> RuleCheck:
        return RuleCheck(
            key=rule_key("budget", s.text), kind="budget", label="Indirect costs",
            status=status, reason=reason, quote=s.text, url=s.url, owner="finance", todo=todo,
        )  # fmt: skip

    if re.search(
        r"(?:no|not allow\w*|unallowable|won't fund|does not fund|not fund)\s+(?:\w+\s+){0,2}"
        r"(?:indirect|overhead)"
        r"|(?:indirect|overhead)[^.]{0,30}(?:not allowed|unallowable|not eligible)",
        s.text,
        re.I,
    ):
        return rule(
            "met",
            "This funder doesn't pay indirect costs.",
            "Leave indirect costs out of this budget.",
        )
    cap = _pct(s.text)
    rate = p.financials.indirect_rate if p else None
    if cap is None:
        return rule(
            "unknown",
            "Hope couldn't read the indirect-cost limit.",
            "Check how this funder lets you budget overhead.",
        )
    todo = f"Budget indirect costs at no more than {cap:g}%."
    if rate is None or rate.rate_bps is None:
        return rule(
            "unknown",
            f"Indirect costs are capped at {cap:g}%; your profile has no indirect rate.",
            todo,
        )
    ours = rate.rate_bps / 100
    if ours <= cap:
        return rule("met", f"Your rate ({ours:g}%) is within the {cap:g}% cap.")
    return rule("not_met", f"Your rate is {ours:g}%, above the {cap:g}% cap.", todo)


# --- conditional --------------------------------------------------------------------------------

CONDITIONAL = re.compile(
    r"\bif\b|\bwhen\b|\bunless\b|only (?:for|if|when)|applicants? (?:requesting|with|that|who)"
    r"|(?:requests?|requesting|budgets?)[^.]{0,40}"
    r"(?:more than|over|exceed|above|greater than|less than|under|below)",
    re.I,
)


def check_condition(s: Sourced, p: AgencyProfile | None, ask: Money | None) -> RuleCheck:
    from hope_discovery.answers import owner_for

    def rule(status: RuleStatus, reason: str) -> RuleCheck:
        return RuleCheck(
            key=rule_key("conditional", s.text),
            kind="conditional",
            label=s.text if len(s.text) <= 90 else s.text[:87].rsplit(" ", 1)[0] + "…",
            status=status,
            reason=reason,
            quote=s.text,
            url=s.url,
            owner=owner_for(s.text),
            todo=(
                f"Required for you: {s.text}"
                if status == "applies"
                else f"Check whether this applies to you: {s.text}"
                if status == "unknown"
                else None
            ),
        )

    text = s.text
    if bound := _amount_bound(text, r"request(?:s|ing|ed)?|award|grant(?: amount)?|ask"):
        direction, limit = bound
        if ask is None:
            return rule(
                "unknown", f"Depends on your request ({direction} {usd(limit)}); set your request."
            )
        hit = ask.amount_minor > limit if direction == "above" else ask.amount_minor <= limit
        verb = "over" if direction == "above" else "at most"
        reason = (
            f"Your request is {usd(ask.amount_minor)}; this is for requests {verb} {usd(limit)}."
        )
        return rule("applies" if hit else "not_applicable", reason)
    if p and (bound := _amount_bound(text, r"budget|revenue|expenses")):
        direction, limit = bound
        ours = p.financials.annual_operating_budget.amount_minor
        hit = ours > limit if direction == "above" else ours <= limit
        verb = "over" if direction == "above" else "at most"
        return rule(
            "applies" if hit else "not_applicable",
            f"Your annual budget is {usd(ours)}; this is for organizations {verb} {usd(limit)}.",
        )
    if p and re.search(r"fiscal(?:ly)? spons", text, re.I):
        sponsored = p.legal.tax_status == "fiscally_sponsored" or bool(p.legal.fiscal_sponsor_id)
        return rule(
            "applies" if sponsored else "not_applicable",
            "You apply through a fiscal sponsor."
            if sponsored
            else "You don't use a fiscal sponsor.",
        )
    if p and re.search(r"single audit|federal (?:funds|awards|expenditures)", text, re.I):
        return rule("unknown", "Depends on how much federal money you spent last year.")
    return rule("unknown", "Hope can't tell from your profile whether this applies to you.")


def check_rules(
    req: Requirements | None, profile: AgencyProfile | None, ask: Money | None
) -> list[RuleCheck]:
    if req is None:
        return []
    deadline = req.submission.deadline_date
    out: list[RuleCheck] = []
    if profile:
        out += [check_eligibility(s, profile, deadline) for s in req.eligibility]
    out += check_budget(req, profile, ask)
    conditions = list(req.conditions)
    seen = {c.text for c in conditions}
    for att in req.attachments:
        if att.quote not in seen and CONDITIONAL.search(att.quote):
            conditions.append(Sourced(text=att.quote, url=att.url))
            seen.add(att.quote)
    out += [check_condition(c, profile, ask) for c in conditions]
    unique: dict[str, RuleCheck] = {}
    for r in out:
        unique.setdefault(r.key, r)
    return list(unique.values())


def apply_staff(rules: list[RuleCheck], evidence: dict[str, dict[str, object]]) -> list[RuleCheck]:
    """Staff can settle what code can't: 'yes' means met (or applies), 'no' not met (or
    doesn't apply). Their note becomes the reason."""
    out = []
    for r in rules:
        e = evidence.get(r.key)
        if not e or e.get("status") not in ("yes", "no"):
            out.append(r)
            continue
        yes = e["status"] == "yes"
        if r.kind == "conditional":
            status: RuleStatus = "applies" if yes else "not_applicable"
        else:
            status = "met" if yes else "not_met"
        note = str(e.get("note") or "").strip()
        reason = f"Confirmed by staff{': ' + note if note else '.'}"
        out.append(
            r.model_copy(update={"status": status, "reason": reason, "confirmed_by_staff": True})
        )
    return out
