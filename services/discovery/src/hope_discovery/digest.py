"""ProfileDigest: the profile facts the model may see, each with an id and a profile path."""

from __future__ import annotations

from dataclasses import dataclass, field

from hope_core.schemas.agency_profile import AgencyProfile

BUDGET_BANDS = [
    (250_000_00, "under $250K"),
    (1_000_000_00, "$250K-$1M"),
    (5_000_000_00, "$1M-$5M"),
    (25_000_000_00, "$5M-$25M"),
]


@dataclass(frozen=True)
class DigestLine:
    ref: str  # "P1"
    path: str  # "programs.0.description"
    text: str


@dataclass
class ProfileDigest:
    lines: list[DigestLine] = field(default_factory=list)
    focus_areas: list[str] = field(default_factory=list)
    programs: list[str] = field(default_factory=list)
    service_area: list[str] = field(default_factory=list)
    forbidden: list[str] = field(default_factory=list)  # names and EIN; never in a query

    def add(self, path: str, text: str) -> None:
        text = " ".join(text.split())
        if text:
            self.lines.append(DigestLine(f"P{len(self.lines) + 1}", path, text[:500]))

    def by_ref(self) -> dict[str, DigestLine]:
        return {line.ref: line for line in self.lines}

    def render(self) -> str:
        return "\n".join(f"[{line.ref}] {line.path}: {line.text}" for line in self.lines)


def budget_band(amount_minor: int) -> str:
    return next((label for limit, label in BUDGET_BANDS if amount_minor < limit), "over $25M")


def build_digest(profile: AgencyProfile, location: str | None = None) -> ProfileDigest:
    d = ProfileDigest(
        focus_areas=list(profile.mission.focus_areas),
        programs=[p.name for p in profile.programs[:6]],
        service_area=list(profile.service_area),
        forbidden=[
            n for n in [profile.legal.legal_name, *profile.legal.dba, profile.legal.ein] if n
        ],
    )
    d.add("mission.mission_statement", profile.mission.mission_statement)
    if profile.mission.values:
        d.add("mission.values", ", ".join(profile.mission.values))
    if profile.mission.focus_areas:
        d.add("mission.focus_areas", ", ".join(profile.mission.focus_areas))
    if profile.mission.ntee_codes:
        d.add("mission.ntee_codes", ", ".join(profile.mission.ntee_codes))
    if profile.service_area:
        d.add("service_area", ", ".join(profile.service_area))
    if location:
        d.add("request.location", location)
    d.add(
        "financials.annual_operating_budget",
        f"Annual budget {budget_band(profile.financials.annual_operating_budget.amount_minor)}",
    )
    for i, program in enumerate(profile.programs[:6]):
        d.add(f"programs.{i}.name", program.name)
        d.add(f"programs.{i}.description", program.description[:300])
        for j, demo in enumerate(program.target_demographics[:2]):
            d.add(f"programs.{i}.target_demographics.{j}.population", demo.population)
    d.add("legal.tax_status", profile.legal.tax_status)
    return d
