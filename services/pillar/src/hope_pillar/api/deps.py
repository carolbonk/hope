from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from typing import Annotated, Any

from fastapi import Depends, HTTPException, Request, status
from hope_core.db import connect, tenant_tx
from hope_core.envelope import PillarEnvelope
from hope_core.pillar import OutboundPackage, RouteReceipt
from hope_core.settings import get_settings

from hope_pillar.api.header_auth import Principal, get_principal
from hope_pillar.outbox import Cursor
from hope_pillar.pillar import KafkaPostgresPillar
from hope_pillar.router import PillarRouter, RouteRejected

Presigner = Callable[[str, str, int], str]
"""(object key, content type, expires seconds) -> pre-signed PUT URL."""

UPLOAD_EXPIRES_SECONDS = 900


def s3_presigner() -> Presigner:
    import boto3

    settings = get_settings()
    client: Any = boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint,
        aws_access_key_id=settings.s3_access_key,
        aws_secret_access_key=settings.s3_secret_key,
    )

    def presign(key: str, content_type: str, expires: int) -> str:
        params = {"Bucket": settings.s3_bucket, "Key": key, "ContentType": content_type}
        return str(client.generate_presigned_url("put_object", Params=params, ExpiresIn=expires))

    return presign


@dataclass
class Services:
    pillar: KafkaPostgresPillar
    router: PillarRouter
    database_url: str
    bucket: str = field(default_factory=lambda: get_settings().s3_bucket)
    presigner_factory: Callable[[], Presigner] = s3_presigner
    _presigner: Presigner | None = field(default=None, init=False)

    @classmethod
    def from_settings(cls) -> Services:
        pillar = KafkaPostgresPillar()
        return cls(pillar, PillarRouter(pillar, pillar.dead_letters), pillar.url)

    @property
    def presign(self) -> Presigner:
        if self._presigner is None:
            self._presigner = self.presigner_factory()
        return self._presigner


def get_services(request: Request) -> Services:
    services: Services = request.app.state.services
    return services


@dataclass
class Tx:
    """One request-scoped tenant transaction; publishes go to the outbox inside it."""

    cur: Cursor
    principal: Principal
    services: Services

    def publish(self, envelope: PillarEnvelope) -> None:
        with self.services.pillar.using(self.cur):
            try:
                self.services.router.route(envelope)
            except RouteRejected as exc:
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc

    def route_outbound(self, package: OutboundPackage) -> RouteReceipt:
        with self.services.pillar.using(self.cur):
            return self.services.pillar.route_outbound(package)


def tenant_transaction(
    principal: Annotated[Principal, Depends(get_principal)],
    services: Annotated[Services, Depends(get_services)],
) -> Iterator[Tx]:
    with connect(services.database_url) as conn, tenant_tx(conn, principal.tenant_id) as cur:
        yield Tx(cur, principal, services)


TxDep = Annotated[Tx, Depends(tenant_transaction)]
