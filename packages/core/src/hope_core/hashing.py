"""Canonical JSON and content hashes. Approvals bind to these hashes (blueprint 4.4)."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from pydantic import BaseModel


def canonical_json(value: BaseModel | dict[str, Any] | list[Any]) -> str:
    data = value.model_dump(mode="json") if isinstance(value, BaseModel) else value
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def content_hash(value: BaseModel | dict[str, Any] | list[Any]) -> str:
    return "sha256:" + hashlib.sha256(canonical_json(value).encode()).hexdigest()
