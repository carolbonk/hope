"""Request principal. Dev/test reads X-Hope-* headers; an OIDC dependency replaces
`get_principal` later (app.dependency_overrides or a new implementation) without touching routes."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import Header, HTTPException, status
from pydantic import BaseModel


class Principal(BaseModel):
    tenant_id: UUID
    user_id: str
    roles: frozenset[str] = frozenset()
    mfa: bool = False


def get_principal(
    x_hope_tenant: Annotated[UUID | None, Header()] = None,
    x_hope_user: Annotated[str, Header()] = "anonymous",
    x_hope_roles: Annotated[str, Header(description="comma-separated roles")] = "",
    x_hope_mfa: Annotated[bool, Header(description="step-up MFA completed")] = False,
) -> Principal:
    if x_hope_tenant is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "X-Hope-Tenant header required")
    roles = frozenset(r.strip() for r in x_hope_roles.split(",") if r.strip())
    return Principal(tenant_id=x_hope_tenant, user_id=x_hope_user, roles=roles, mfa=x_hope_mfa)
