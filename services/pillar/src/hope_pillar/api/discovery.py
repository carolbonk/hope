"""Discovery routes (H2). Empty until H2 fills them in."""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/v1", tags=["discovery"])
