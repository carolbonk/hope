"""Cost basis lookup. Rates come from HRIS/ERP/profile records, never from a proposal."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol

from hope_budget.contracts import CostBasisRecord


class CostBasisResolver(Protocol):
    def resolve(self, ref: str) -> CostBasisRecord | None: ...

    def catalog(self) -> list[CostBasisRecord]: ...


class InMemoryCostBasisResolver:
    def __init__(self, records: Iterable[CostBasisRecord] = ()) -> None:
        self._records: dict[str, CostBasisRecord] = {}
        for record in records:
            self.add(record)

    def add(self, record: CostBasisRecord) -> None:
        if record.ref in self._records:
            raise ValueError(f"duplicate cost basis ref {record.ref}")
        self._records[record.ref] = record

    def resolve(self, ref: str) -> CostBasisRecord | None:
        return self._records.get(ref)

    def catalog(self) -> list[CostBasisRecord]:
        return [self._records[ref] for ref in sorted(self._records)]
