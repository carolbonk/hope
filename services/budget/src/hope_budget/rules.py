"""Agency rates and grantor rules, normalized from the shared contracts."""

from __future__ import annotations

from typing import Any, Literal

from hope_core.money import Bps, CurrencyCode, Money
from hope_core.schemas.agency_profile import AgencyProfile
from hope_core.schemas.common import Provenance
from hope_core.schemas.grant_opportunity import Funding
from pydantic import BaseModel, ConfigDict

IndirectBase = Literal["MTDC", "TDC", "salaries_wages"]

DE_MINIMIS_BPS = 1500
"""2 CFR 200.414(f) de minimis indirect rate."""

SUBAWARD_MTDC_THRESHOLD_MINOR = 25_000_00
"""Portion of each subaward included in MTDC (2 CFR 200.1). Override per award if needed."""

PROFILE_REF = "profile:financials"
FUNDING_REF = "opportunity:funding"


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class AgencyRates(_Frozen):
    fringe_rate_bps: Bps | None = None
    indirect_type: Literal["negotiated_nicra", "de_minimis", "none"] = "none"
    indirect_rate_bps: Bps | None = None
    indirect_base: IndirectBase | None = None
    provenance: Provenance | None = None

    @classmethod
    def from_profile(cls, profile: AgencyProfile) -> AgencyRates:
        fin = profile.financials
        rate = fin.indirect_rate
        return cls(
            fringe_rate_bps=fin.fringe_rate_bps,
            indirect_type=rate.type if rate else "none",
            indirect_rate_bps=rate.rate_bps if rate else None,
            indirect_base=rate.base if rate else None,
            provenance=fin.provenance,
        )

    def indirect_bps(self) -> int:
        if self.indirect_type == "de_minimis":
            return min(
                DE_MINIMIS_BPS if self.indirect_rate_bps is None else self.indirect_rate_bps,
                DE_MINIMIS_BPS,
            )
        if self.indirect_type == "negotiated_nicra":
            return self.indirect_rate_bps or 0
        return 0


class BudgetRules(_Frozen):
    currency: CurrencyCode = "USD"
    award_ceiling: Money | None = None
    award_floor: Money | None = None
    cost_share_ratio_bps: Bps | None = None
    cost_share_in_kind_allowed: bool = True
    indirect_allowed: bool = True
    indirect_cap_bps: Bps | None = None
    indirect_base: IndirectBase | None = None
    unallowable_costs: tuple[str, ...] = ()
    subaward_mtdc_threshold_minor: int = SUBAWARD_MTDC_THRESHOLD_MINOR

    @classmethod
    def from_funding(cls, funding: Funding, **overrides: Any) -> BudgetRules:
        share = funding.cost_share
        policy = funding.indirect_cost_policy
        reference = funding.award_ceiling or funding.award_floor
        values: dict[str, Any] = {
            "currency": reference.currency if reference else "USD",
            "award_ceiling": funding.award_ceiling,
            "award_floor": funding.award_floor,
            "cost_share_ratio_bps": share.ratio_bps if share and share.required else None,
            "cost_share_in_kind_allowed": share.in_kind_allowed is not False if share else True,
            "indirect_allowed": policy.allowed if policy else True,
            "indirect_cap_bps": policy.cap_bps if policy else None,
            "indirect_base": policy.base if policy and policy.base != "unspecified" else None,
            "unallowable_costs": tuple(funding.unallowable_costs),
        }
        values.update(overrides)
        return cls(**values)


def effective_indirect(agency: AgencyRates, rules: BudgetRules) -> tuple[int, str, IndirectBase]:
    """Rate actually charged: min(funder cap, agency NICRA/de minimis), with its source ref."""
    base = rules.indirect_base or agency.indirect_base or "MTDC"
    if not rules.indirect_allowed:
        return 0, f"{FUNDING_REF}.indirect_cost_policy.allowed", base
    agency_bps = agency.indirect_bps()
    cap = rules.indirect_cap_bps
    if cap is not None and cap < agency_bps:
        return cap, f"{FUNDING_REF}.indirect_cost_policy.cap_bps", base
    return agency_bps, f"{PROFILE_REF}.indirect_rate", base


def indirect_limit_bps(agency: AgencyRates, rules: BudgetRules) -> int:
    """The ceiling the indirect_cap check is held against."""
    if not rules.indirect_allowed:
        return 0
    return agency.indirect_bps() if rules.indirect_cap_bps is None else rules.indirect_cap_bps
