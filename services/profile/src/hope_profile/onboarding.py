"""H1 hackathon profile form: the wire shape of SC11/SC09, its mapping onto `AgencyProfile`, field
errors with stable codes, and code-only completeness. No LLM runs here."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Annotated, Any, Literal

from hope_core.money import Money
from hope_core.schemas.agency_profile import AgencyProfile, BudgetBand, TaxStatus
from hope_core.schemas.common import Provenance
from hope_core.settings import HopeSettings
from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    HttpUrl,
    StringConstraints,
    ValidationError,
    field_validator,
)
from pydantic_core import PydanticCustomError

from hope_profile import ntee
from hope_profile.validators import derive_budget_band, ein_errors, parse_fiscal_year_end

US_STATES = frozenset(
    [
        "AL",
        "AK",
        "AZ",
        "AR",
        "CA",
        "CO",
        "CT",
        "DE",
        "DC",
        "FL",
        "GA",
        "HI",
        "ID",
        "IL",
        "IN",
        "IA",
        "KS",
        "KY",
        "LA",
        "ME",
        "MD",
        "MA",
        "MI",
        "MN",
        "MS",
        "MO",
        "MT",
        "NE",
        "NV",
        "NH",
        "NJ",
        "NM",
        "NY",
        "NC",
        "ND",
        "OH",
        "OK",
        "OR",
        "PA",
        "PR",
        "RI",
        "SC",
        "SD",
        "TN",
        "TX",
        "UT",
        "VT",
        "VA",
        "WA",
        "WV",
        "WI",
        "WY",
    ]
)

BAND_MIDPOINT_MINOR: dict[str, int] = {
    "<250k": 12_500_000,
    "250k-1m": 50_000_000,
    "1m-5m": 250_000_000,
    "5m-25m": 1_000_000_000,
    ">25m": 3_000_000_000,
}
EXACT = "exact"
MIDPOINT = "budget_band_midpoint"
SECTIONS = ("basics", "mission", "ntee_codes", "budget", "programs")

EIN_FORMAT = "Enter your EIN as 12-3456789."
EIN_PREFIX = "This EIN prefix isn't assigned by the IRS. Check the number."

ErrorCode = Literal[
    "required",
    "too_short",
    "too_long",
    "invalid_format",
    "invalid_ein_prefix",
    "unknown_state",
    "unknown_ntee_code",
    "too_many",
    "duplicate",
]


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out = []
    for v in values:
        if v.casefold() not in seen:
            seen.add(v.casefold())
            out.append(v)
    return out


ServiceArea = Annotated[str, StringConstraints(min_length=2, max_length=80)]
Value = Annotated[str, StringConstraints(min_length=2, max_length=60)]


class _Form(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Basics(_Form):
    legal_name: str = Field(min_length=2, max_length=200)
    ein: str = Field(pattern=r"^[0-9]{2}-[0-9]{7}$")
    tax_status: TaxStatus = "501c3_public_charity"
    hq_city: str = Field(min_length=2, max_length=80)
    hq_state: str = Field(pattern=r"^[A-Z]{2}$")
    service_area: list[ServiceArea] = Field(min_length=1, max_length=20)
    website: HttpUrl | None = None

    @field_validator("ein")
    @classmethod
    def _ein_prefix(cls, v: str) -> str:
        if ein_errors(v):
            raise PydanticCustomError("invalid_ein_prefix", EIN_PREFIX)
        return v

    @field_validator("hq_state")
    @classmethod
    def _state(cls, v: str) -> str:
        if v not in US_STATES:
            raise PydanticCustomError("unknown_state", "Pick a US state.")
        return v


class MissionForm(_Form):
    mission_statement: str = Field(min_length=20, max_length=2000)
    vision_statement: str | None = Field(None, max_length=2000)
    values: Annotated[list[Value], AfterValidator(_dedupe)] = Field(default=[], max_length=10)


class BudgetForm(_Form):
    budget_band: BudgetBand
    annual_operating_budget_usd: int | None = Field(None, ge=0, le=10_000_000_000)
    fiscal_year_end: str = Field("12-31", pattern=r"^(0[1-9]|1[0-2])-(0[1-9]|[12][0-9]|3[01])$")

    @field_validator("fiscal_year_end")
    @classmethod
    def _calendar_date(cls, v: str) -> str:
        try:
            parse_fiscal_year_end(v)
        except ValueError:
            raise PydanticCustomError("invalid_format", "Enter a real date as MM-DD.") from None
        return v


class ProgramForm(_Form):
    program_id: str | None = Field(None, max_length=80)
    name: str = Field(min_length=2, max_length=120)
    description: str = Field(min_length=20, max_length=1000)
    people_served: str = Field(min_length=2, max_length=200)
    annual_served: int | None = Field(None, ge=0, le=100_000_000)
    age_range: str | None = Field(None, max_length=40)


def _check_codes(codes: list[str]) -> list[str]:
    unknown = [c for c in codes if not ntee.is_code(c)]
    if unknown:
        raise PydanticCustomError("unknown_ntee_code", "Pick codes from the NTEE list.")
    if len(set(codes)) != len(codes):
        raise PydanticCustomError("duplicate", "Each code can be picked once.")
    return codes


def _check_programs(programs: list[ProgramForm]) -> list[ProgramForm]:
    ids = [p.program_id for p in programs if p.program_id]
    if len(set(ids)) != len(ids):
        raise PydanticCustomError("duplicate", "Each program needs its own id.")
    return programs


NteeCodes = Annotated[list[str], AfterValidator(_check_codes)]
Programs = Annotated[list[ProgramForm], AfterValidator(_check_programs)]


class ProfileForm(_Form):
    basics: Basics
    mission: MissionForm
    ntee_codes: NteeCodes = Field(min_length=1, max_length=3)
    budget: BudgetForm
    programs: Programs = Field(min_length=1, max_length=10)


class ProfilePatch(_Form):
    """`PATCH /v1/profile`: whole top-level sections; at least one."""

    basics: Basics | None = None
    mission: MissionForm | None = None
    ntee_codes: NteeCodes | None = Field(None, min_length=1, max_length=3)
    budget: BudgetForm | None = None
    programs: Programs | None = Field(None, min_length=1, max_length=10)


class Completeness(BaseModel):
    score: int = Field(ge=0, le=100)
    missing: list[str]
    suggestions: list[str]


class ProfileView(BaseModel):
    """The GET/PUT/PATCH `/v1/profile` body (`contracts/mocks/w2/profile.get/ok.json`)."""

    version: int
    updated_at: datetime
    updated_by: str
    onboarding_complete: bool
    form: ProfileForm
    ntee_labels: dict[str, str]
    completeness: Completeness


# --- field errors ----------------------------------------------------------------------------


class FieldError(BaseModel):
    field: str
    code: ErrorCode
    message: str


_CUSTOM: frozenset[str] = frozenset(
    {"invalid_ein_prefix", "unknown_state", "unknown_ntee_code", "duplicate", "invalid_format"}
)


def _code_and_message(err: Any) -> tuple[ErrorCode, str]:
    kind = str(err["type"])
    ctx = err.get("ctx") or {}
    field = ".".join(str(p) for p in err["loc"])
    if kind in _CUSTOM:
        return kind, str(err["msg"])  # type: ignore[return-value]
    if kind == "missing" or (kind == "string_too_short" and not str(err.get("input", "")).strip()):
        return "required", "This field is required."
    if kind == "too_short":
        if field == "ntee_codes":
            return "required", "Pick at least one NTEE code."
        return "required", "Add at least one."
    if kind == "string_too_short":
        return "too_short", f"Write at least {ctx.get('min_length')} characters."
    if kind == "string_too_long":
        return "too_long", f"Keep it under {ctx.get('max_length')} characters."
    if kind == "too_long":
        if field == "ntee_codes":
            return "too_many", "You can pick up to 3 codes."
        return "too_many", f"Add at most {ctx.get('max_length')}."
    if field == "basics.ein":
        return "invalid_format", EIN_FORMAT
    return "invalid_format", "Check the format of this field."


def field_errors(exc: ValidationError) -> list[FieldError]:
    out = []
    for err in exc.errors():
        code, message = _code_and_message(err)
        field = ".".join(str(p) for p in err["loc"]) or "body"
        out.append(FieldError(field=field, code=code, message=message))
    return out


def profile_error_fields(errors: list[str]) -> list[FieldError]:
    """Map `validators.profile_errors` strings (raised by `_normalize`) onto form fields."""
    out = []
    for msg in errors:
        if msg.startswith("legal.ein"):
            out.append(
                FieldError(field="basics.ein", code="invalid_ein_prefix", message=EIN_PREFIX)
            )
        elif msg.startswith("financials.fiscal_year_end"):
            out.append(
                FieldError(
                    field="budget.fiscal_year_end",
                    code="invalid_format",
                    message="Enter a real date as MM-DD.",
                )
            )
        else:
            out.append(FieldError(field="body", code="invalid_format", message=msg))
    return out


# --- form <-> AgencyProfile ------------------------------------------------------------------


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:60] or "program"


def assign_program_ids(programs: list[ProgramForm]) -> list[ProgramForm]:
    taken = {p.program_id for p in programs if p.program_id}
    out = []
    for p in programs:
        if not p.program_id:
            base = f"prg-{_slug(p.name)}"
            pid, n = base, 2
            while pid in taken:
                pid, n = f"{base}-{n}", n + 1
            taken.add(pid)
            p = p.model_copy(update={"program_id": pid})
        out.append(p)
    return out


def form_to_profile(
    form: ProfileForm,
    base: AgencyProfile | None,
    settings: HopeSettings,
    now: datetime | None = None,
) -> dict[str, Any]:
    """The candidate `AgencyProfile` JSON for `ProfileRepository.save_direct`. Fields the form
    doesn't cover come from `base`, or from enterprise defaults."""
    now = now or datetime.now(UTC)
    old: dict[str, Any] = base.model_dump(mode="json") if base else {}
    b, m, bud = form.basics, form.mission, form.budget

    legal = {
        **old.get("legal", {}),
        "legal_name": b.legal_name,
        "ein": b.ein,
        "tax_status": b.tax_status,
        "hq_city": b.hq_city,
        "hq_state": b.hq_state,
        "website": str(b.website) if b.website else None,
    }
    legal["state_of_incorporation"] = legal.get("state_of_incorporation") or b.hq_state

    mission = {
        **old.get("mission", {}),
        "mission_statement": m.mission_statement,
        "vision_statement": m.vision_statement,
        "values": list(m.values),
        "ntee_codes": list(form.ntee_codes),
        "focus_areas": [ntee.label(c) or c for c in form.ntee_codes],
    }

    if bud.annual_operating_budget_usd is not None:
        amount, source_ref = bud.annual_operating_budget_usd * 100, EXACT
    else:
        amount, source_ref = BAND_MIDPOINT_MINOR[bud.budget_band], MIDPOINT
    old_fin = old.get("financials", {})
    old_prov = old_fin.get("provenance") or {}
    unchanged = (
        old_fin.get("annual_operating_budget", {}).get("amount_minor") == amount
        and old_prov.get("source_ref") == source_ref
    )
    provenance = (
        old_prov
        if unchanged
        else Provenance(source="user_input", source_ref=source_ref, captured_at=now).model_dump(
            mode="json"
        )
    )
    financials = {
        **old_fin,
        "fiscal_year_end": bud.fiscal_year_end,
        "annual_operating_budget": Money(amount_minor=amount, currency="USD").model_dump(
            mode="json"
        ),
        "provenance": provenance,
    }

    old_programs = {p["program_id"]: p for p in old.get("programs", [])}
    programs = []
    for p in assign_program_ids(form.programs):
        assert p.program_id is not None
        prev = old_programs.get(p.program_id, {})
        programs.append(
            {
                **prev,
                "program_id": p.program_id,
                "name": p.name,
                "description": p.description,
                "status": prev.get("status", "active"),
                "target_demographics": [
                    {
                        "population": p.people_served,
                        "age_range": p.age_range,
                        "annual_served": p.annual_served,
                    }
                ],
            }
        )

    return {
        **old,
        "agency_id": str(settings.agency_id),
        "tenant_id": str(settings.tenant_id),
        "version": old.get("version", 1),
        "service_area": list(b.service_area),
        "legal": legal,
        "mission": mission,
        "financials": financials,
        "programs": programs,
        "approval_hierarchy": old.get("approval_hierarchy")
        or [{"gate": "HITL-0", "approver_roles": ["admin"]}],
    }


def _url(value: str | None) -> HttpUrl | None:
    if not value:
        return None
    try:
        return HttpUrl(value)
    except ValidationError:
        return None


def profile_to_form(profile: AgencyProfile) -> ProfileForm:
    """The inverse of `form_to_profile`. Built without re-validation, so an older profile that
    misses a form field still renders (SC11 then asks for it)."""
    legal, fin = profile.legal, profile.financials
    midpoint = bool(fin.provenance and fin.provenance.source_ref == MIDPOINT)
    band = fin.budget_band or derive_budget_band(fin.annual_operating_budget) or "<250k"
    programs = []
    for p in profile.programs:
        demo = p.target_demographics[0] if p.target_demographics else None
        programs.append(
            ProgramForm.model_construct(
                program_id=p.program_id,
                name=p.name,
                description=p.description,
                people_served=demo.population if demo else "",
                annual_served=demo.annual_served if demo else None,
                age_range=demo.age_range if demo else None,
            )
        )
    return ProfileForm.model_construct(
        basics=Basics.model_construct(
            legal_name=legal.legal_name,
            ein=legal.ein,
            tax_status=legal.tax_status,
            hq_city=legal.hq_city or "",
            hq_state=legal.hq_state or "",
            service_area=list(profile.service_area),
            website=_url(legal.website),
        ),
        mission=MissionForm.model_construct(
            mission_statement=profile.mission.mission_statement,
            vision_statement=profile.mission.vision_statement,
            values=list(profile.mission.values),
        ),
        ntee_codes=list(profile.mission.ntee_codes),
        budget=BudgetForm.model_construct(
            budget_band=band,
            annual_operating_budget_usd=None
            if midpoint
            else fin.annual_operating_budget.amount_minor // 100,
            fiscal_year_end=fin.fiscal_year_end,
        ),
        programs=programs,
    )


def form_json(form: ProfileForm) -> dict[str, Any]:
    data: dict[str, Any] = form.model_dump(mode="json", warnings=False)
    return data


def form_completeness(form: ProfileForm) -> Completeness:
    """12 equally weighted checks; `missing` lists failing form paths in form order."""
    b, m = form.basics, form.mission
    checks: list[list[tuple[str, str]]] = []

    def check(ok: bool, *missing: tuple[str, str]) -> None:
        checks.append([] if ok else list(missing))

    check(bool(b.legal_name.strip()), ("basics.legal_name", "Add your legal name"))
    check(bool(b.ein.strip()), ("basics.ein", "Add your EIN"))
    hq = [
        *([] if b.hq_city.strip() else [("basics.hq_city", "Add your headquarters city")]),
        *([] if b.hq_state.strip() else [("basics.hq_state", "Add your headquarters state")]),
    ]
    check(not hq, *hq)
    check(bool(b.service_area), ("basics.service_area", "Add the area you serve"))
    check(bool(b.website), ("basics.website", "Add your website"))
    check(
        len(m.mission_statement.strip()) >= 20,
        ("mission.mission_statement", "Write a mission statement of at least 20 characters"),
    )
    check(bool((m.vision_statement or "").strip()), ("mission.vision_statement", "Add a vision"))
    check(len(m.values) >= 2, ("mission.values", "Add at least two values"))
    check(bool(form.ntee_codes), ("ntee_codes", "Pick an NTEE code"))
    check(
        form.budget.annual_operating_budget_usd is not None,
        ("budget.annual_operating_budget_usd", "Add your exact annual operating budget"),
    )
    check(bool(form.programs), ("programs", "Add at least one program"))
    gaps: list[tuple[str, str]] = []
    for i, p in enumerate(form.programs):
        if p.annual_served is None:
            gaps.append((f"programs.{i}.annual_served", f"Add the number served for {p.name}"))
        if not (p.age_range or "").strip():
            gaps.append((f"programs.{i}.age_range", f"Add the age range for {p.name}"))
    check(not gaps, *gaps)

    passed = sum(1 for c in checks if not c)
    failing = [item for c in checks for item in c]
    return Completeness(
        score=round(100 * passed / len(checks)),
        missing=[path for path, _ in failing],
        suggestions=[text for _, text in failing],
    )


def onboarding_complete(profile: AgencyProfile) -> bool:
    """Same rule as H0's `/v1/me`."""
    return bool(profile.mission.mission_statement.strip() and profile.programs)
