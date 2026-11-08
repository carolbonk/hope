"""The SC11 onboarding form (`ProfileForm`, the `/v1/profile` wire shape) and its mapping to and
from `AgencyProfile`. Pure code: no I/O and no LLM."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Literal

from hope_core.money import Money
from hope_core.schemas.agency_profile import AgencyProfile, BudgetBand, TaxStatus
from hope_core.schemas.common import Provenance
from hope_core.schemas.hitl import Gate
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    HttpUrl,
    ValidationError,
    field_serializer,
    field_validator,
)
from pydantic_core import PydanticCustomError

from hope_profile import ntee
from hope_profile.validators import INVALID_EIN_PREFIXES, derive_budget_band

US_STATES: dict[str, str] = {
    "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas", "CA": "California",
    "CO": "Colorado", "CT": "Connecticut", "DE": "Delaware", "DC": "District of Columbia",
    "FL": "Florida", "GA": "Georgia", "HI": "Hawaii", "ID": "Idaho", "IL": "Illinois",
    "IN": "Indiana", "IA": "Iowa", "KS": "Kansas", "KY": "Kentucky", "LA": "Louisiana",
    "ME": "Maine", "MD": "Maryland", "MA": "Massachusetts", "MI": "Michigan", "MN": "Minnesota",
    "MS": "Mississippi", "MO": "Missouri", "MT": "Montana", "NE": "Nebraska", "NV": "Nevada",
    "NH": "New Hampshire", "NJ": "New Jersey", "NM": "New Mexico", "NY": "New York",
    "NC": "North Carolina", "ND": "North Dakota", "OH": "Ohio", "OK": "Oklahoma", "OR": "Oregon",
    "PA": "Pennsylvania", "PR": "Puerto Rico", "RI": "Rhode Island", "SC": "South Carolina",
    "SD": "South Dakota", "TN": "Tennessee", "TX": "Texas", "UT": "Utah", "VT": "Vermont",
    "VA": "Virginia", "WA": "Washington", "WV": "West Virginia", "WI": "Wisconsin",
    "WY": "Wyoming",
}  # fmt: skip

# Representative `annual_operating_budget` (minor units) for a band-only budget.
BAND_MIDPOINT_MINOR: dict[str, int] = {
    "<250k": 12_500_000,
    "250k-1m": 50_000_000,
    "1m-5m": 250_000_000,
    "5m-25m": 1_000_000_000,
    ">25m": 3_000_000_000,
}
EXACT = "exact"
BAND_MIDPOINT = "budget_band_midpoint"
SECTIONS = ("basics", "mission", "ntee_codes", "budget", "programs")

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


def _texts(values: list[str], lo: int, hi: int) -> list[str]:
    cleaned = [v.strip() for v in values]
    for value in cleaned:
        if len(value) < lo:
            raise PydanticCustomError("too_short", "Write at least {n} characters.", {"n": lo})
        if len(value) > hi:
            raise PydanticCustomError("too_long", "Keep it under {n} characters.", {"n": hi})
    return cleaned


class _Form(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Basics(_Form):
    legal_name: str = Field(min_length=2, max_length=200)
    ein: str = Field(pattern=r"^[0-9]{2}-[0-9]{7}$")
    tax_status: TaxStatus = "501c3_public_charity"
    hq_city: str = Field(min_length=2, max_length=80)
    hq_state: str = Field(pattern=r"^[A-Z]{2}$")
    service_area: list[str] = Field(min_length=1, max_length=20)
    website: HttpUrl | None = None

    @field_validator("ein")
    @classmethod
    def _ein_prefix(cls, value: str) -> str:
        if value[:2] in INVALID_EIN_PREFIXES:
            raise PydanticCustomError(
                "invalid_ein_prefix", "This EIN prefix isn't assigned by the IRS. Check the number."
            )
        return value

    @field_validator("hq_state")
    @classmethod
    def _state(cls, value: str) -> str:
        if value not in US_STATES:
            raise PydanticCustomError("unknown_state", "Pick a US state.")
        return value

    @field_validator("service_area")
    @classmethod
    def _service_area(cls, value: list[str]) -> list[str]:
        return _texts(value, 2, 80)

    @field_validator("website", mode="before")
    @classmethod
    def _blank_website(cls, value: object) -> object:
        return None if isinstance(value, str) and not value.strip() else value

    @field_serializer("website")
    def _website(self, value: HttpUrl | None) -> str | None:
        return str(value) if value is not None else None


class MissionForm(_Form):
    mission_statement: str = Field(min_length=20, max_length=2000)
    vision_statement: str | None = Field(None, max_length=2000)
    values: list[str] = Field(default=[], max_length=10)

    @field_validator("vision_statement")
    @classmethod
    def _blank_vision(cls, value: str | None) -> str | None:
        return value or None

    @field_validator("values")
    @classmethod
    def _values(cls, value: list[str]) -> list[str]:
        unique: dict[str, str] = {}
        for item in _texts(value, 2, 60):
            unique.setdefault(item.casefold(), item)
        return list(unique.values())


class BudgetForm(_Form):
    budget_band: BudgetBand
    annual_operating_budget_usd: int | None = Field(None, ge=0, le=10_000_000_000)
    fiscal_year_end: str = Field("12-31", pattern=r"^(0[1-9]|1[0-2])-(0[1-9]|[12][0-9]|3[01])$")


class ProgramForm(_Form):
    program_id: str | None = None
    name: str = Field(min_length=2, max_length=120)
    description: str = Field(min_length=20, max_length=1000)
    people_served: str = Field(min_length=2, max_length=200)
    annual_served: int | None = Field(None, ge=0, le=100_000_000)
    age_range: str | None = Field(None, max_length=40)

    @field_validator("program_id", "age_range")
    @classmethod
    def _blank(cls, value: str | None) -> str | None:
        return value or None


def _ntee_codes(value: list[str]) -> list[str]:
    codes = [c.strip().upper() for c in value]
    if len(set(codes)) != len(codes):
        raise PydanticCustomError("duplicate", "Each NTEE code can be picked once.")
    for code in codes:
        if not ntee.is_code(code):
            raise PydanticCustomError("unknown_ntee_code", "Pick a code from the NTEE list.")
    return codes


def _program_ids(programs: list[ProgramForm]) -> list[ProgramForm]:
    ids = [p.program_id for p in programs if p.program_id]
    if len(set(ids)) != len(ids):
        raise PydanticCustomError("duplicate", "Each program needs its own id.")
    return programs


class ProfileForm(_Form):
    basics: Basics
    mission: MissionForm
    ntee_codes: list[str] = Field(min_length=1, max_length=3)
    budget: BudgetForm
    programs: list[ProgramForm] = Field(min_length=1, max_length=10)

    _check_ntee = field_validator("ntee_codes")(_ntee_codes)
    _check_programs = field_validator("programs")(_program_ids)


class ProfilePatchBody(_Form):
    """Whole top-level sections to replace; at least one."""

    basics: Basics | None = None
    mission: MissionForm | None = None
    ntee_codes: list[str] | None = Field(None, min_length=1, max_length=3)
    budget: BudgetForm | None = None
    programs: list[ProgramForm] | None = Field(None, min_length=1, max_length=10)

    _check_ntee = field_validator("ntee_codes")(_ntee_codes)
    _check_programs = field_validator("programs")(_program_ids)


class FieldError(BaseModel):
    field: str
    code: ErrorCode
    message: str


class FormCompleteness(BaseModel):
    score: int = Field(ge=0, le=100)
    missing: list[str]
    suggestions: list[str]


class ProfileView(BaseModel):
    version: int
    updated_at: datetime
    updated_by: str
    onboarding_complete: bool
    form: ProfileForm
    ntee_labels: dict[str, str]
    completeness: FormCompleteness


# --- validation errors -----------------------------------------------------------------------

_LABELS = {
    "legal_name": "Legal name",
    "ein": "EIN",
    "tax_status": "Tax status",
    "hq_city": "City",
    "hq_state": "State",
    "service_area": "Service area",
    "website": "Website",
    "mission_statement": "Mission statement",
    "vision_statement": "Vision",
    "values": "Values",
    "budget_band": "Budget",
    "annual_operating_budget_usd": "Annual budget",
    "fiscal_year_end": "Fiscal year end",
    "programs": "Program",
    "name": "Program name",
    "description": "Description",
    "people_served": "People served",
    "annual_served": "People served each year",
    "age_range": "Age range",
    "body": "A section",
}
_FORMAT_MESSAGES = {
    "ein": "Enter your EIN as 12-3456789.",
    "hq_state": "Pick a US state.",
    "website": "Enter a full web address, like https://example.org.",
    "fiscal_year_end": "Enter the fiscal year end as MM-DD.",
}
_CUSTOM: frozenset[str] = frozenset(
    {
        "invalid_ein_prefix",
        "unknown_state",
        "unknown_ntee_code",
        "duplicate",
        "too_short",
        "too_long",
    }
)


_REQUEST_PARTS = frozenset({"body", "query", "path", "header", "cookie"})


def _field_name(path: str) -> str:
    return next((p for p in reversed(path.split(".")) if not p.isdigit()), path)


def field_error(
    path: str, kind: str, ctx: dict[str, Any] | None, given: object, msg: str
) -> FieldError:
    """Map one Pydantic error to the wire `FieldError` with SC11 copy."""
    ctx = ctx or {}
    name = _field_name(path)
    label = _LABELS.get(name, name.replace("_", " ").capitalize())
    empty = given is None or (isinstance(given, str | list | dict) and len(given) == 0)
    if kind in _CUSTOM and "field_type" not in ctx:
        return FieldError.model_validate({"field": path, "code": kind, "message": msg})
    if kind == "missing" or (kind in ("string_too_short", "too_short") and empty):
        if name == "ntee_codes":
            return FieldError(field=path, code="required", message="Pick at least one NTEE code.")
        return FieldError(field=path, code="required", message=f"{label} is required.")
    if kind == "string_too_short":
        n = ctx.get("min_length", 1)
        return FieldError(field=path, code="too_short", message=f"Write at least {n} characters.")
    if kind == "string_too_long":
        n = ctx.get("max_length", 0)
        return FieldError(field=path, code="too_long", message=f"Keep it under {n} characters.")
    if kind == "too_long":
        if name == "ntee_codes":
            return FieldError(field=path, code="too_many", message="You can pick up to 3 codes.")
        n = ctx.get("max_length", 0)
        return FieldError(field=path, code="too_many", message=f"Add at most {n}.")
    if kind == "too_short":
        n = ctx.get("min_length", 1)
        return FieldError(field=path, code="required", message=f"Add at least {n}.")
    message = _FORMAT_MESSAGES.get(name, f"Check the {label.lower()}.")
    return FieldError(field=path, code="invalid_format", message=message)


def validation_errors(
    exc: ValidationError | list[dict[str, Any]], prefix: tuple[str, ...] = ()
) -> list[FieldError]:
    errors = exc.errors() if isinstance(exc, ValidationError) else exc
    out: list[FieldError] = []
    for err in errors:
        loc = [str(p) for p in err["loc"]]
        if loc and loc[0] in _REQUEST_PARTS:
            loc = loc[1:]
        loc = [*prefix, *loc]
        path = ".".join(loc) or "body"
        out.append(
            field_error(path, str(err["type"]), err.get("ctx"), err.get("input"), str(err["msg"]))
        )
    return out


def profile_error(message: str) -> FieldError:
    """Map a `validators.profile_errors` / `_normalize` message to a form-path error."""
    if message.startswith("legal.ein"):
        if "prefix" in message:
            return FieldError(
                field="basics.ein",
                code="invalid_ein_prefix",
                message="This EIN prefix isn't assigned by the IRS. Check the number.",
            )
        return FieldError(
            field="basics.ein", code="invalid_format", message=_FORMAT_MESSAGES["ein"]
        )
    if message.startswith("financials.fiscal_year_end"):
        return FieldError(
            field="budget.fiscal_year_end",
            code="invalid_format",
            message="Enter a real calendar date as MM-DD.",
        )
    return FieldError(field="body", code="invalid_format", message=message)


# --- form <-> profile ------------------------------------------------------------------------


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:40] or "program"


def _program_ids_for(programs: list[ProgramForm]) -> list[str]:
    taken = {p.program_id for p in programs if p.program_id}
    ids: list[str] = []
    for program in programs:
        if program.program_id:
            ids.append(program.program_id)
            continue
        base = f"prg-{slug(program.name)}"
        candidate, n = base, 2
        while candidate in taken:
            candidate, n = f"{base}-{n}", n + 1
        taken.add(candidate)
        ids.append(candidate)
    return ids


def form_to_profile(
    form: ProfileForm,
    base: AgencyProfile | None,
    *,
    tenant_id: Any,
    agency_id: Any,
    now: datetime,
) -> dict[str, Any]:
    """The `AgencyProfile` (as JSON) the form describes. Fields the form doesn't cover come from
    `base`, or defaults that satisfy the enterprise-required fields."""
    old = base.model_dump(mode="json") if base else {}
    b, m, money = form.basics, form.mission, form.budget

    legal = dict(old.get("legal") or {})
    legal.update(
        legal_name=b.legal_name,
        ein=b.ein,
        tax_status=b.tax_status,
        hq_city=b.hq_city,
        hq_state=b.hq_state,
        website=str(b.website) if b.website else None,
    )
    legal["state_of_incorporation"] = legal.get("state_of_incorporation") or b.hq_state

    mission = dict(old.get("mission") or {})
    mission.update(
        mission_statement=m.mission_statement,
        vision_statement=m.vision_statement,
        values=m.values,
        ntee_codes=form.ntee_codes,
        focus_areas=[ntee.label(c) for c in form.ntee_codes],
    )

    if money.annual_operating_budget_usd is not None:
        amount, source_ref = money.annual_operating_budget_usd * 100, EXACT
    else:
        amount, source_ref = BAND_MIDPOINT_MINOR[money.budget_band], BAND_MIDPOINT
    financials = dict(old.get("financials") or {})
    budget = Money(amount_minor=amount, currency="USD").model_dump(mode="json")
    old_provenance = financials.get("provenance") or {}
    unchanged = (
        financials.get("annual_operating_budget") == budget
        and old_provenance.get("source") == "user_input"
        and old_provenance.get("source_ref") == source_ref
    )
    financials.update(
        fiscal_year_end=money.fiscal_year_end,
        annual_operating_budget=budget,
        provenance=old_provenance
        if unchanged
        else Provenance(source="user_input", source_ref=source_ref, captured_at=now).model_dump(
            mode="json"
        ),
    )

    old_programs = {p["program_id"]: p for p in old.get("programs") or []}
    programs = []
    for program, program_id in zip(form.programs, _program_ids_for(form.programs), strict=True):
        kept = dict(old_programs.get(program_id) or {"status": "active"})
        demographics = list(kept.get("target_demographics") or [])
        first = {
            "population": program.people_served,
            "age_range": program.age_range,
            "annual_served": program.annual_served,
        }
        kept.update(
            program_id=program_id,
            name=program.name,
            description=program.description,
            target_demographics=[first, *demographics[1:]],
        )
        programs.append(kept)

    default_rule = {"gate": Gate.PROFILE_COMMIT.value, "approver_roles": ["admin"]}
    return {
        **old,
        "agency_id": str(agency_id),
        "tenant_id": str(tenant_id),
        "version": old.get("version", 0) + 1,
        "service_area": b.service_area,
        "legal": legal,
        "mission": mission,
        "financials": financials,
        "programs": programs,
        "approval_hierarchy": old.get("approval_hierarchy") or [default_rule],
    }


def profile_to_form(profile: AgencyProfile, extras: dict[str, Any] | None = None) -> ProfileForm:
    """The inverse of `form_to_profile`. HQ and website come from the `agency_profile_extras` row
    when given, else from `legal` (which carries the same values)."""
    legal, fin, extras = profile.legal, profile.financials, extras or {}
    exact = not (fin.provenance and fin.provenance.source_ref == BAND_MIDPOINT)
    band = fin.budget_band or derive_budget_band(fin.annual_operating_budget) or "<250k"
    programs = []
    for p in profile.programs:
        demo = p.target_demographics[0] if p.target_demographics else None
        programs.append(
            {
                "program_id": p.program_id,
                "name": p.name,
                "description": p.description,
                "people_served": demo.population if demo else "",
                "annual_served": demo.annual_served if demo else None,
                "age_range": demo.age_range if demo else None,
            }
        )
    return ProfileForm.model_validate(
        {
            "basics": {
                "legal_name": legal.legal_name,
                "ein": legal.ein,
                "tax_status": legal.tax_status,
                "hq_city": extras.get("hq_city") or legal.hq_city or "",
                "hq_state": extras.get("hq_state") or legal.hq_state or "",
                "service_area": profile.service_area,
                "website": extras.get("website") if extras else legal.website,
            },
            "mission": {
                "mission_statement": profile.mission.mission_statement,
                "vision_statement": profile.mission.vision_statement,
                "values": profile.mission.values,
            },
            "ntee_codes": profile.mission.ntee_codes,
            "budget": {
                "budget_band": band,
                "annual_operating_budget_usd": fin.annual_operating_budget.amount_minor // 100
                if exact
                else None,
                "fiscal_year_end": fin.fiscal_year_end,
            },
            "programs": programs,
        }
    )


def merge_sections(form: ProfileForm, patch: ProfilePatchBody) -> ProfileForm:
    """Replace the given top-level sections of `form` (PATCH)."""
    data = form.model_dump(mode="json")
    data.update(patch.model_dump(mode="json", exclude_unset=True, exclude_none=True))
    return ProfileForm.model_validate(data)


# --- completeness ----------------------------------------------------------------------------


def form_completeness(form: ProfileForm) -> FormCompleteness:
    """12 equal-weight checks; `missing` lists failing form paths in form order."""
    b, m = form.basics, form.mission
    checks: list[tuple[bool, list[tuple[str, str]]]] = [
        (bool(b.legal_name), [("basics.legal_name", "Add your legal name")]),
        (bool(b.ein), [("basics.ein", "Add your EIN")]),
        (
            bool(b.hq_city and b.hq_state),
            [("basics.hq_city", "Add the city and state of your headquarters")],
        ),
        (bool(b.service_area), [("basics.service_area", "Add the areas you serve")]),
        (b.website is not None, [("basics.website", "Add your website")]),
        (len(m.mission_statement) >= 20, [("mission.mission_statement", "Describe your mission")]),
        (bool(m.vision_statement), [("mission.vision_statement", "Add your vision")]),
        (len(m.values) >= 2, [("mission.values", "Add at least 2 values")]),
        (bool(form.ntee_codes), [("ntee_codes", "Pick an NTEE code")]),
        (
            form.budget.annual_operating_budget_usd is not None,
            [("budget.annual_operating_budget_usd", "Add your exact annual budget")],
        ),
        (bool(form.programs), [("programs", "Add a program")]),
    ]
    details: list[tuple[str, str]] = []
    for i, p in enumerate(form.programs):
        if p.annual_served is None:
            details.append(
                (f"programs.{i}.annual_served", f"Add how many people {p.name} serves each year")
            )
        if p.age_range is None:
            details.append((f"programs.{i}.age_range", f"Add the age range for {p.name}"))
    checks.append((not details, details))
    failing = [item for ok, items in checks if not ok for item in items]
    passed = sum(1 for ok, _ in checks if ok)
    return FormCompleteness(
        score=round(100 * passed / len(checks)),
        missing=[path for path, _ in failing],
        suggestions=[text for _, text in failing],
    )


def onboarding_complete(form: ProfileForm) -> bool:
    return bool(form.mission.mission_statement.strip() and form.programs)
