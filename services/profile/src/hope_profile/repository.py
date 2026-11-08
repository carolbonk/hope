"""ProfileRepository: bitemporal agency profiles, HITL-0 change proposals and stale alerts.

All reads and writes go through `tenant_tx` as `hope_app`, so RLS scopes every query. Events
are published to the PillarPort only after the transaction commits.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from datetime import UTC, date, datetime
from typing import Any, Literal, cast
from uuid import UUID, uuid4

import psycopg
from hope_core.db import tenant_tx
from hope_core.envelope import PillarEnvelope, Producer
from hope_core.hashing import content_hash
from hope_core.pillar import PillarPort
from hope_core.schemas.agency_profile import AgencyProfile
from hope_core.schemas.common import Contract, Provenance
from hope_core.schemas.hitl import Gate, HitlDecision, HitlRequest
from hope_core.topics import EventType
from psycopg.types.json import Jsonb
from pydantic import BaseModel, ValidationError

from hope_profile.contracts import (
    SCHEMA_VERSION,
    CompletenessReport,
    FieldChange,
    ProfileChangeProposal,
    ProfileUpdated,
    StaleFieldAlert,
)
from hope_profile.diff import META_FIELDS, diff, merge_patch, paths_overlap
from hope_profile.validators import (
    completeness,
    derive_budget_band,
    hitl0_roles,
    profile_errors,
    stale_fields,
)

Conn = psycopg.Connection[dict[str, object]]
Cursor = psycopg.Cursor[dict[str, object]]
PRODUCER = Producer(service="hope-profile", agent_id="A3")


class ProfileError(Exception):
    pass


class ProfileNotFoundError(ProfileError):
    pass


class VersionConflictError(ProfileError):
    pass


class ProfileValidationError(ProfileError):
    def __init__(self, errors: list[str]) -> None:
        super().__init__("; ".join(errors))
        self.errors = errors


class ProposalStateError(ProfileError):
    pass


class SeparationOfDutiesError(ProfileError):
    pass


class ApproverRoleError(ProfileError):
    pass


class ProfileVersion(BaseModel):
    version: int
    profile: AgencyProfile
    valid_from: datetime
    valid_to: datetime | None
    recorded_at: datetime
    recorded_by: str


class ChangeResult(BaseModel):
    status: Literal["committed", "pending_approval", "rejected", "no_change"]
    version: int
    changes: list[FieldChange]
    proposal: ProfileChangeProposal | None = None


def proposal_hash(p: ProfileChangeProposal) -> str:
    """The HITL-0 artifact hash: everything the approver is shown, nothing decided later."""
    fields = {"proposal_id", "tenant_id", "agency_id", "base_version", "patch", "changes"}
    return content_hash(p.model_dump(mode="json", include=fields | {"provenance", "proposed_by"}))


def _utcnow() -> datetime:
    return datetime.now(UTC)


_VERSION_COLS = "version, profile, valid_from, valid_to, recorded_at, recorded_by"


class ProfileRepository:
    def __init__(
        self, conn: Conn, pillar: PillarPort, *, clock: Callable[[], datetime] = _utcnow
    ) -> None:
        self.conn = conn
        self.pillar = pillar
        self.clock = clock

    # Reads

    def create_agency(
        self, tenant_id: UUID, profile: AgencyProfile, created_by: str
    ) -> ProfileVersion:
        if profile.tenant_id != tenant_id:
            raise ProfileValidationError(["profile.tenant_id does not match the tenant"])
        data = self._normalize(profile.model_dump(mode="json"), version=1)
        with tenant_tx(self.conn, tenant_id) as cur:
            cur.execute(
                "INSERT INTO agencies (agency_id, tenant_id, legal_name) VALUES (%s, %s, %s)",
                (profile.agency_id, tenant_id, profile.legal.legal_name),
            )
            created = self._insert_version(cur, tenant_id, data, created_by)
            changes = diff({}, data)
            self._audit(cur, tenant_id, created_by, "profile.created", profile.agency_id, {})
        self._publish_updated(tenant_id, created, None, changes, created_by)
        return created

    def current(self, tenant_id: UUID, agency_id: UUID) -> ProfileVersion:
        return self.as_of(tenant_id, agency_id, None)

    def as_of(self, tenant_id: UUID, agency_id: UUID, as_of: datetime | None) -> ProfileVersion:
        """The version valid at `as_of` (business time); None means now."""
        with tenant_tx(self.conn, tenant_id) as cur:
            cur.execute(
                f"SELECT {_VERSION_COLS} FROM agency_profile_versions"
                " WHERE agency_id = %s AND valid_from <= %s ORDER BY version DESC LIMIT 1",
                (agency_id, as_of or self.clock()),
            )
            return self._one_version(cur, agency_id)

    def get_version(self, tenant_id: UUID, agency_id: UUID, version: int) -> ProfileVersion:
        with tenant_tx(self.conn, tenant_id) as cur:
            cur.execute(
                f"SELECT {_VERSION_COLS} FROM agency_profile_versions"
                " WHERE agency_id = %s AND version = %s",
                (agency_id, version),
            )
            return self._one_version(cur, agency_id)

    def history(self, tenant_id: UUID, agency_id: UUID) -> list[ProfileVersion]:
        with tenant_tx(self.conn, tenant_id) as cur:
            cur.execute(
                f"SELECT {_VERSION_COLS} FROM agency_profile_versions"
                " WHERE agency_id = %s ORDER BY version",
                (agency_id,),
            )
            rows = cur.fetchall()
        if not rows:
            raise ProfileNotFoundError(str(agency_id))
        return [_version(row) for row in rows]

    def diff(
        self, tenant_id: UUID, agency_id: UUID, from_version: int, to_version: int
    ) -> list[FieldChange]:
        old = self.get_version(tenant_id, agency_id, from_version).profile
        new = self.get_version(tenant_id, agency_id, to_version).profile
        return diff(old.model_dump(mode="json"), new.model_dump(mode="json"))

    def completeness(self, tenant_id: UUID, agency_id: UUID) -> CompletenessReport:
        return completeness(self.current(tenant_id, agency_id).profile)

    def proposals(
        self, tenant_id: UUID, agency_id: UUID, status: str | None = "pending"
    ) -> list[ProfileChangeProposal]:
        with tenant_tx(self.conn, tenant_id) as cur:
            cur.execute(
                "SELECT * FROM profile_change_proposals WHERE agency_id = %s"
                " AND (%s::text IS NULL OR status = %s) ORDER BY proposed_at",
                (agency_id, status, status),
            )
            return [_proposal(row) for row in cur.fetchall()]

    # Writes

    def propose(
        self,
        tenant_id: UUID,
        agency_id: UUID,
        patch: dict[str, Any],
        proposed_by: str,
        *,
        expected_version: int | None = None,
        provenance: Provenance | None = None,
        require_review: bool = False,
    ) -> ChangeResult:
        """Commit unprotected changes directly; park protected ones (or any change that needs
        review, such as an LLM extraction) as a HITL-0 proposal."""
        if META_FIELDS & patch.keys():
            raise ProfileValidationError([f"{sorted(META_FIELDS & patch.keys())} are read-only"])
        if provenance is not None:
            patch = _with_provenance(patch, provenance)
        with tenant_tx(self.conn, tenant_id) as cur:
            latest = self._latest_for_update(cur, agency_id)
            if expected_version is not None and expected_version != latest.version:
                raise VersionConflictError(
                    f"expected v{expected_version}, current v{latest.version}"
                )
            old = latest.profile.model_dump(mode="json")
            new = self._apply(old, patch, latest.version + 1)
            changes = diff(old, new)
            if not changes:
                return ChangeResult(status="no_change", version=latest.version, changes=[])
            if require_review or any(c.protected for c in changes):
                proposal = self._insert_proposal(
                    cur,
                    tenant_id,
                    agency_id,
                    latest.version,
                    patch,
                    changes,
                    provenance,
                    proposed_by,
                )
                pending = True
            else:
                committed = self._commit(cur, tenant_id, latest, new, proposed_by, changes)
                pending = False
        if pending:
            self._publish_proposed(proposal, hitl0_roles(latest.profile))
            return ChangeResult(
                status="pending_approval",
                version=latest.version,
                changes=changes,
                proposal=proposal,
            )
        self._publish_updated(tenant_id, committed, latest.version, changes, proposed_by)
        return ChangeResult(status="committed", version=committed.version, changes=changes)

    def decide(
        self, tenant_id: UUID, decision: HitlDecision, approver_roles: Sequence[str]
    ) -> ChangeResult:
        """Apply a HITL-0 decision. The decision must carry the proposal's current hash."""
        if decision.gate != Gate.PROFILE_COMMIT:
            raise ProposalStateError(f"{decision.gate} is not the profile commit gate")
        if decision.decision not in ("approve", "reject", "request_changes"):
            raise ProposalStateError(f"unsupported HITL-0 decision {decision.decision!r}")
        committed: ProfileVersion | None = None
        with tenant_tx(self.conn, tenant_id) as cur:
            cur.execute(
                "SELECT * FROM profile_change_proposals WHERE proposal_id = %s FOR UPDATE",
                (decision.request_id,),
            )
            row = cur.fetchone()
            if row is None:
                raise ProfileNotFoundError(f"proposal {decision.request_id}")
            proposal = _proposal(row)
            if proposal.status != "pending":
                raise ProposalStateError(f"proposal is already {proposal.status}")
            if proposal_hash(proposal) != proposal.content_hash:
                raise ProposalStateError("proposal content does not match its hash")
            if decision.artifact_hash != proposal.content_hash:
                raise ProposalStateError("approval hash is stale; review the current proposal")
            if decision.decided_by == proposal.proposed_by:
                raise SeparationOfDutiesError("the proposer cannot decide their own change")
            latest = self._latest_for_update(cur, proposal.agency_id)
            required = hitl0_roles(latest.profile)
            if not set(required) & set(approver_roles):
                raise ApproverRoleError(f"HITL-0 needs one of {list(required)}")

            changes = proposal.changes
            if decision.decision == "approve":
                old = latest.profile.model_dump(mode="json")
                if latest.version != proposal.base_version:
                    self._check_rebase(cur, proposal, old)
                new = self._apply(old, proposal.patch, latest.version + 1)
                changes = diff(old, new)
                committed = self._commit(cur, tenant_id, latest, new, decision.decided_by, changes)
            status = "approved" if committed else "rejected"
            cur.execute(
                "UPDATE profile_change_proposals SET status = %s, decided_by = %s,"
                " decided_at = %s, decision_comment = %s, committed_version = %s"
                " WHERE proposal_id = %s RETURNING *",
                (
                    status,
                    decision.decided_by,
                    decision.decided_at,
                    decision.comment,
                    committed.version if committed else None,
                    proposal.proposal_id,
                ),
            )
            proposal = _proposal(_fetch(cur))
            cur.execute(
                "INSERT INTO approvals (tenant_id, workflow_id, gate, decision, artifact_hash,"
                " decided_by, decided_at, comment) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                (
                    tenant_id,
                    _workflow_id(proposal),
                    decision.gate.value,
                    decision.decision,
                    decision.artifact_hash,
                    decision.decided_by,
                    decision.decided_at,
                    decision.comment,
                ),
            )
            self._audit(
                cur,
                tenant_id,
                decision.decided_by,
                f"profile.proposal_{status}",
                proposal.agency_id,
                {"proposal_id": str(proposal.proposal_id), "hash": proposal.content_hash},
            )
        self._publish(EventType.HITL_DECIDED, tenant_id, proposal.agency_id, decision)
        if committed is None:
            return ChangeResult(
                status="rejected", version=latest.version, changes=changes, proposal=proposal
            )
        self._publish_updated(
            tenant_id,
            committed,
            latest.version,
            changes,
            proposal.proposed_by,
            proposal_id=proposal.proposal_id,
            approved_by=decision.decided_by,
        )
        return ChangeResult(
            status="committed", version=committed.version, changes=changes, proposal=proposal
        )

    def latest(self, tenant_id: UUID, agency_id: UUID) -> ProfileVersion | None:
        """The newest version (by number), or None before the first save."""
        with tenant_tx(self.conn, tenant_id) as cur:
            cur.execute(
                f"SELECT {_VERSION_COLS} FROM agency_profile_versions"
                " WHERE agency_id = %s ORDER BY version DESC LIMIT 1",
                (agency_id,),
            )
            row = cur.fetchone()
        return _version(row) if row else None

    def save_direct(
        self,
        tenant_id: UUID,
        agency_id: UUID,
        data: dict[str, Any],
        actor: str,
        expected_version: int | None,
    ) -> ProfileVersion:
        """Commit `data` as the next version with no HITL-0 proposal (hackathon). With no
        version yet it creates the agency and version 1; otherwise `expected_version` must be
        the latest version. A no-op save returns the current version unchanged."""
        if data.get("agency_id") != str(agency_id) or data.get("tenant_id") != str(tenant_id):
            raise ProfileValidationError(["profile agency_id/tenant_id do not match"])
        committed: ProfileVersion | None = None
        with tenant_tx(self.conn, tenant_id) as cur:
            legal_name = str(data.get("legal", {}).get("legal_name") or "")
            cur.execute(
                "INSERT INTO agencies (agency_id, tenant_id, legal_name) VALUES (%s, %s, %s)"
                " ON CONFLICT (agency_id) DO NOTHING",
                (agency_id, tenant_id, legal_name),
            )
            cur.execute(
                "SELECT agency_id FROM agencies WHERE agency_id = %s FOR UPDATE", (agency_id,)
            )
            cur.execute(
                f"SELECT {_VERSION_COLS} FROM agency_profile_versions WHERE agency_id = %s"
                " ORDER BY version DESC LIMIT 1 FOR UPDATE",
                (agency_id,),
            )
            row = cur.fetchone()
            latest = _version(row) if row else None
            current = latest.version if latest else None
            if expected_version != current:
                raise VersionConflictError(f"expected v{expected_version}, current v{current}")
            if latest is None:
                new = self._normalize(data, version=1)
                changes = diff({}, new)
                committed = self._insert_version(cur, tenant_id, new, actor)
                cur.execute(
                    "UPDATE agencies SET legal_name = %s WHERE agency_id = %s",
                    (committed.profile.legal.legal_name, agency_id),
                )
                self._audit(
                    cur,
                    tenant_id,
                    actor,
                    "profile.updated",
                    agency_id,
                    {"version": 1, "paths": [c.path for c in changes]},
                )
            else:
                old = latest.profile.model_dump(mode="json")
                new = self._normalize(data, version=latest.version + 1)
                changes = diff(old, new)
                if not changes:
                    return latest
                committed = self._commit(cur, tenant_id, latest, new, actor, changes)
            self._upsert_extras(cur, tenant_id, committed, actor)
        self._publish_updated(tenant_id, committed, current, changes, actor)
        return committed

    def extras(self, tenant_id: UUID, agency_id: UUID) -> dict[str, Any] | None:
        with tenant_tx(self.conn, tenant_id) as cur:
            cur.execute(
                "SELECT hq_city, hq_state, website FROM agency_profile_extras WHERE agency_id = %s",
                (agency_id,),
            )
            row = cur.fetchone()
        return dict(row) if row else None

    def _upsert_extras(
        self, cur: Cursor, tenant_id: UUID, committed: ProfileVersion, actor: str
    ) -> None:
        legal = committed.profile.legal
        if not (legal.hq_city and legal.hq_state):
            return
        cur.execute(
            "INSERT INTO agency_profile_extras"
            " (agency_id, tenant_id, hq_city, hq_state, website, updated_at, updated_by)"
            " VALUES (%s, %s, %s, %s, %s, now(), %s)"
            " ON CONFLICT (agency_id) DO UPDATE SET hq_city = EXCLUDED.hq_city,"
            " hq_state = EXCLUDED.hq_state, website = EXCLUDED.website,"
            " updated_at = EXCLUDED.updated_at, updated_by = EXCLUDED.updated_by",
            (
                committed.profile.agency_id,
                tenant_id,
                legal.hq_city,
                legal.hq_state,
                legal.website,
                actor,
            ),
        )

    def scan_stale(
        self, tenant_id: UUID, agency_id: UUID, today: date | None = None
    ) -> list[StaleFieldAlert]:
        """Emit `profile.stale_field` once per (field, threshold, date)."""
        profile = self.current(tenant_id, agency_id).profile
        fresh: list[StaleFieldAlert] = []
        with tenant_tx(self.conn, tenant_id) as cur:
            for alert in stale_fields(profile, today or self.clock().date()):
                cur.execute(
                    "INSERT INTO profile_stale_alerts (tenant_id, agency_id, field, threshold,"
                    " ref_date) VALUES (%s, %s, %s, %s, %s) ON CONFLICT DO NOTHING",
                    (tenant_id, agency_id, alert.field, alert.threshold, alert.ref_date),
                )
                if cur.rowcount:
                    fresh.append(alert)
        for alert in fresh:
            self._publish(EventType.PROFILE_STALE_FIELD, tenant_id, agency_id, alert)
        return fresh

    # Internals

    def _normalize(self, data: dict[str, Any], version: int) -> dict[str, Any]:
        """Validate a candidate profile and set code-owned fields (version, budget_band)."""
        data = {**data, "version": version, "valid_from": None}
        try:
            profile = AgencyProfile.model_validate(data)
        except ValidationError as exc:
            raise ProfileValidationError(
                [f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in exc.errors()]
            ) from exc
        errors = profile_errors(profile, self.clock().date())
        if errors:
            raise ProfileValidationError(errors)
        profile.financials.budget_band = derive_budget_band(
            profile.financials.annual_operating_budget
        )
        return profile.model_dump(mode="json")

    def _apply(self, old: dict[str, Any], patch: dict[str, Any], version: int) -> dict[str, Any]:
        return self._normalize(cast(dict[str, Any], merge_patch(old, patch)), version)

    def _latest_for_update(self, cur: Cursor, agency_id: UUID) -> ProfileVersion:
        cur.execute(
            f"SELECT {_VERSION_COLS} FROM agency_profile_versions WHERE agency_id = %s"
            " ORDER BY version DESC LIMIT 1 FOR UPDATE",
            (agency_id,),
        )
        return self._one_version(cur, agency_id)

    def _one_version(self, cur: Cursor, agency_id: UUID) -> ProfileVersion:
        row = cur.fetchone()
        if row is None:
            raise ProfileNotFoundError(str(agency_id))
        return _version(row)

    def _insert_version(
        self, cur: Cursor, tenant_id: UUID, data: dict[str, Any], recorded_by: str
    ) -> ProfileVersion:
        cur.execute(
            "INSERT INTO agency_profile_versions"
            " (agency_id, tenant_id, version, profile, valid_from, recorded_by)"
            f" VALUES (%s, %s, %s, %s, %s, %s) RETURNING {_VERSION_COLS}",
            (data["agency_id"], tenant_id, data["version"], Jsonb(data), self.clock(), recorded_by),
        )
        return _version(_fetch(cur))

    def _commit(
        self,
        cur: Cursor,
        tenant_id: UUID,
        latest: ProfileVersion,
        new: dict[str, Any],
        actor: str,
        changes: list[FieldChange],
    ) -> ProfileVersion:
        committed = self._insert_version(cur, tenant_id, new, actor)
        cur.execute(
            "UPDATE agency_profile_versions SET valid_to = %s"
            " WHERE agency_id = %s AND version = %s",
            (committed.valid_from, latest.profile.agency_id, latest.version),
        )
        if latest.profile.legal.legal_name != committed.profile.legal.legal_name:
            cur.execute(
                "UPDATE agencies SET legal_name = %s WHERE agency_id = %s",
                (committed.profile.legal.legal_name, latest.profile.agency_id),
            )
        self._audit(
            cur,
            tenant_id,
            actor,
            "profile.updated",
            latest.profile.agency_id,
            {"version": committed.version, "paths": [c.path for c in changes]},
        )
        return committed

    def _insert_proposal(
        self,
        cur: Cursor,
        tenant_id: UUID,
        agency_id: UUID,
        base_version: int,
        patch: dict[str, Any],
        changes: list[FieldChange],
        provenance: Provenance | None,
        proposed_by: str,
    ) -> ProfileChangeProposal:
        draft = ProfileChangeProposal(
            proposal_id=uuid4(),
            tenant_id=tenant_id,
            agency_id=agency_id,
            base_version=base_version,
            patch=patch,
            changes=changes,
            provenance=provenance,
            content_hash="",
            proposed_by=proposed_by,
            proposed_at=self.clock(),
        )
        proposal = draft.model_copy(update={"content_hash": proposal_hash(draft)})
        data = proposal.model_dump(mode="json")
        cur.execute(
            "INSERT INTO profile_change_proposals (proposal_id, tenant_id, agency_id,"
            " base_version, patch, diff, provenance, content_hash, proposed_by, proposed_at)"
            " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (
                proposal.proposal_id,
                tenant_id,
                agency_id,
                base_version,
                Jsonb(data["patch"]),
                Jsonb(data["changes"]),
                Jsonb(data["provenance"]) if provenance else None,
                proposal.content_hash,
                proposed_by,
                proposal.proposed_at,
            ),
        )
        self._audit(
            cur,
            tenant_id,
            proposed_by,
            "profile.change_proposed",
            agency_id,
            {"proposal_id": str(proposal.proposal_id), "hash": proposal.content_hash},
        )
        return proposal

    def _check_rebase(
        self, cur: Cursor, proposal: ProfileChangeProposal, latest: dict[str, Any]
    ) -> None:
        """A proposal may land on a newer version only if nobody touched the same paths since."""
        cur.execute(
            "SELECT profile FROM agency_profile_versions WHERE agency_id = %s AND version = %s",
            (proposal.agency_id, proposal.base_version),
        )
        base = cast(dict[str, Any], _fetch(cur)["profile"])
        since = [c.path for c in diff(base, latest)]
        mine = [c.path for c in proposal.changes]
        clashes = sorted({a for a in mine for b in since if paths_overlap(a, b)})
        if clashes:
            raise VersionConflictError(f"changed since the proposal was made: {clashes}")

    def _audit(
        self,
        cur: Cursor,
        tenant_id: UUID,
        actor: str,
        action: str,
        agency_id: UUID,
        detail: dict[str, Any],
    ) -> None:
        cur.execute(
            "INSERT INTO audit_log (tenant_id, actor, action, subject, detail)"
            " VALUES (%s, %s, %s, %s, %s)",
            (tenant_id, actor, action, f"agency:{agency_id}", Jsonb(detail)),
        )

    def _publish(
        self, event_type: EventType, tenant_id: UUID, agency_id: UUID, payload: Contract
    ) -> None:
        self.pillar.publish(
            PillarEnvelope(
                event_type=event_type,
                schema_ref=_schema_ref(payload),
                tenant_id=tenant_id,
                subject_id=str(agency_id),
                producer=PRODUCER,
                data_classification="confidential",
                payload=payload.model_dump(mode="json"),
            )
        )

    def _publish_updated(
        self,
        tenant_id: UUID,
        committed: ProfileVersion,
        previous_version: int | None,
        changes: list[FieldChange],
        committed_by: str,
        **extra: Any,
    ) -> None:
        payload = ProfileUpdated(
            agency_id=committed.profile.agency_id,
            version=committed.version,
            previous_version=previous_version,
            changes=changes,
            protected_changed=any(c.protected for c in changes),
            committed_by=committed_by,
            **extra,
        )
        self._publish(EventType.PROFILE_UPDATED, tenant_id, payload.agency_id, payload)

    def _publish_proposed(self, proposal: ProfileChangeProposal, roles: Sequence[str]) -> None:
        self._publish(
            EventType.PROFILE_CHANGE_PROPOSED, proposal.tenant_id, proposal.agency_id, proposal
        )
        paths = ", ".join(c.path for c in proposal.changes)
        request = HitlRequest(
            request_id=proposal.proposal_id,
            tenant_id=proposal.tenant_id,
            workflow_id=_workflow_id(proposal),
            gate=Gate.PROFILE_COMMIT,
            artifact_hash=proposal.content_hash,
            approver_roles=list(roles),
            summary=f"Profile change by {proposal.proposed_by}: {paths}",
        )
        self._publish(EventType.HITL_REQUESTED, proposal.tenant_id, proposal.agency_id, request)


def _workflow_id(proposal: ProfileChangeProposal) -> str:
    return f"profile-proposal:{proposal.proposal_id}"


def _with_provenance(patch: dict[str, Any], provenance: Provenance) -> dict[str, Any]:
    """Stamp provenance onto every touched section that carries a provenance field."""
    stamped = dict(patch)
    for section in ("legal", "financials"):
        if isinstance(stamped.get(section), dict):
            stamped[section] = {
                **stamped[section],
                "provenance": provenance.model_dump(mode="json"),
            }
    return stamped


def _fetch(cur: Cursor) -> dict[str, object]:
    row = cur.fetchone()
    if row is None:
        raise ProfileNotFoundError("row vanished")
    return row


def _version(row: dict[str, object]) -> ProfileVersion:
    data = dict(row)
    data["profile"] = {**cast(dict[str, Any], row["profile"]), "valid_from": row["valid_from"]}
    return ProfileVersion.model_validate(data)


def _proposal(row: dict[str, object]) -> ProfileChangeProposal:
    data = {k: v for k, v in row.items() if k != "diff"}
    return ProfileChangeProposal.model_validate({**data, "changes": row["diff"]})


def _schema_ref(payload: Contract) -> str:
    name = re.sub(r"(?<!^)(?=[A-Z])", "-", type(payload).__name__).lower()
    return f"{name}/{SCHEMA_VERSION}"
