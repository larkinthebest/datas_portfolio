from datetime import date
from decimal import Decimal

from app.domain.calculations import (
    DepreciationInput,
    UtilityAllocationInput,
    calculate_linear_depreciation,
    calculate_utility_allocation,
    sum_money,
)


def test_linear_depreciation_uses_decimal_months() -> None:
    result = calculate_linear_depreciation(
        DepreciationInput(
            acquisition_cost=Decimal("1200.00"),
            useful_life_months=12,
            start_date=date(2025, 1, 10),
            period_from=date(2025, 1, 1),
            period_to=date(2025, 12, 31),
        )
    )
    assert result.monthly_amount == Decimal("100.00")
    assert result.applicable_months == 12
    assert result.amount_for_period == Decimal("1200.00")


def test_utility_allocation_handles_leap_year() -> None:
    result = calculate_utility_allocation(
        UtilityAllocationInput(
            total_amount=Decimal("3660.00"),
            billing_period_from=date(2024, 1, 1),
            billing_period_to=date(2024, 12, 31),
            allocation_period_from=date(2024, 2, 1),
            allocation_period_to=date(2024, 2, 29),
        )
    )
    assert result.total_days == 366
    assert result.allocated_days == 29
    assert result.allocated_amount == Decimal("290.00")


def test_sum_money_never_uses_float() -> None:
    assert sum_money([Decimal("0.10"), Decimal("0.20")]) == Decimal("0.30")
