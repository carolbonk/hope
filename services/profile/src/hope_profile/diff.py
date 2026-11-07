"""JSON merge patch and field-level diffs over profile documents."""

from __future__ import annotations

from typing import Any

from hope_core.schemas.agency_profile import PROTECTED_PROFILE_PATHS

from hope_profile.contracts import FieldChange

META_FIELDS = frozenset({"agency_id", "tenant_id", "version", "valid_from"})


def is_protected(path: str) -> bool:
    return path.split(".", 1)[0] in PROTECTED_PROFILE_PATHS


def paths_overlap(a: str, b: str) -> bool:
    return a == b or a.startswith(b + ".") or b.startswith(a + ".")


def merge_patch(target: Any, patch: Any) -> Any:
    """RFC 7396: objects merge recursively, null deletes, everything else replaces."""
    if not isinstance(patch, dict):
        return patch
    result = dict(target) if isinstance(target, dict) else {}
    for key, value in patch.items():
        if value is None:
            result.pop(key, None)
        else:
            result[key] = merge_patch(result.get(key), value)
    return result


def diff(old: dict[str, Any], new: dict[str, Any], prefix: str = "") -> list[FieldChange]:
    changes: list[FieldChange] = []
    for key in sorted(old.keys() | new.keys()):
        if not prefix and key in META_FIELDS:
            continue
        path = f"{prefix}{key}"
        a, b = old.get(key), new.get(key)
        if isinstance(a, dict) and isinstance(b, dict):
            changes.extend(diff(a, b, path + "."))
        elif a != b:
            changes.append(FieldChange(path=path, old=a, new=b, protected=is_protected(path)))
    return changes
