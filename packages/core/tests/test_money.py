from decimal import Decimal

import pytest
from hope_core.money import CurrencyMismatchError, Money, sum_money
from hypothesis import given
from hypothesis import strategies as st


def test_from_decimal_rounds_half_up() -> None:
    assert Money.from_decimal("10.005").amount_minor == 1001
    assert Money.from_decimal("1850000").format() == "USD 1,850,000.00"


def test_apply_bps() -> None:
    assert Money(amount_minor=100_000_00).apply_bps(1500).amount_minor == 15_000_00
    assert Money(amount_minor=333).apply_bps(5000).amount_minor == 167


def test_currency_mismatch() -> None:
    with pytest.raises(CurrencyMismatchError):
        _ = Money(amount_minor=1) + Money(amount_minor=1, currency="EUR")


@given(st.lists(st.integers(min_value=-(10**12), max_value=10**12), max_size=50))
def test_sum_is_exact(values: list[int]) -> None:
    assert sum_money([Money(amount_minor=v) for v in values]).amount_minor == sum(values)


@given(st.integers(min_value=0, max_value=10**12), st.integers(min_value=0, max_value=10_000))
def test_apply_bps_never_exceeds_base(amount: int, bps: int) -> None:
    result = Money(amount_minor=amount).apply_bps(bps)
    assert 0 <= result.amount_minor <= amount
    assert abs(Decimal(result.amount_minor) - Decimal(amount) * bps / 10_000) <= Decimal("0.5")
