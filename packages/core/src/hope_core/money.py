"""Integer money in minor units. Floats are never used for money anywhere in Hope."""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

BPS_PER_UNIT = 10_000

Bps = Annotated[int, Field(ge=0, description="basis points, e.g. 1500 = 15%")]
CurrencyCode = Annotated[str, Field(pattern=r"^[A-Z]{3}$")]


class CurrencyMismatchError(ValueError):
    pass


class Money(BaseModel):
    model_config = ConfigDict(frozen=True)

    amount_minor: int
    currency: CurrencyCode = "USD"

    @classmethod
    def zero(cls, currency: str = "USD") -> Money:
        return cls(amount_minor=0, currency=currency)

    @classmethod
    def from_decimal(cls, major: Decimal | str | int, currency: str = "USD") -> Money:
        minor = (Decimal(major) * 100).quantize(Decimal(1), rounding=ROUND_HALF_UP)
        return cls(amount_minor=int(minor), currency=currency)

    def _check(self, other: Money) -> None:
        if self.currency != other.currency:
            raise CurrencyMismatchError(f"{self.currency} != {other.currency}")

    def __add__(self, other: Money) -> Money:
        self._check(other)
        return Money(amount_minor=self.amount_minor + other.amount_minor, currency=self.currency)

    def __sub__(self, other: Money) -> Money:
        self._check(other)
        return Money(amount_minor=self.amount_minor - other.amount_minor, currency=self.currency)

    def __lt__(self, other: Money) -> bool:
        self._check(other)
        return self.amount_minor < other.amount_minor

    def __le__(self, other: Money) -> bool:
        self._check(other)
        return self.amount_minor <= other.amount_minor

    def times(self, quantity: Decimal | int | str) -> Money:
        """Multiply by a quantity, rounding half-up to the minor unit."""
        minor = (Decimal(self.amount_minor) * Decimal(quantity)).quantize(
            Decimal(1), rounding=ROUND_HALF_UP
        )
        return Money(amount_minor=int(minor), currency=self.currency)

    def apply_bps(self, bps: int) -> Money:
        """Return this amount times a basis-point rate (e.g. indirect or fringe)."""
        return self.times(Decimal(bps) / BPS_PER_UNIT)

    def to_decimal(self) -> Decimal:
        return Decimal(self.amount_minor) / 100

    def format(self) -> str:
        sign = "-" if self.amount_minor < 0 else ""
        return f"{sign}{self.currency} {abs(self.to_decimal()):,.2f}"


def sum_money(items: list[Money], currency: str = "USD") -> Money:
    total = Money.zero(currency)
    for item in items:
        total = total + item
    return total
