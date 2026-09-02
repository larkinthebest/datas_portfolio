from __future__ import annotations

import calendar
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from pydantic import BaseModel, Field, model_validator

CENT = Decimal("0.01")


class DepreciationInput(BaseModel):
    acquisition_cost: Decimal = Field(gt=0)
    residual_value: Decimal = Field(default=Decimal("0"), ge=0)
    useful_life_months: int = Field(gt=0)
    start_date: date
    period_from: date
    period_to: date
    rounding_mode: str = ROUND_HALF_UP

    @model_validator(mode="after")
    def validate_period(self) -> DepreciationInput:
        if self.residual_value >= self.acquisition_cost:
            raise ValueError("Residual value must be below acquisition cost")
        if self.period_to < self.period_from:
            raise ValueError("period_to must be on or after period_from")
        return self


class DepreciationResult(BaseModel):
    monthly_amount: Decimal
    applicable_months: int
    amount_for_period: Decimal
    steps: list[str]


def calculate_linear_depreciation(data: DepreciationInput) -> DepreciationResult:
    depreciable = data.acquisition_cost - data.residual_value
    monthly_exact = depreciable / Decimal(data.useful_life_months)
    asset_end = _add_months(data.start_date, data.useful_life_months - 1)
    effective_from = max(_month_start(data.start_date), _month_start(data.period_from))
    effective_to = min(_month_start(asset_end), _month_start(data.period_to))
    months = 0 if effective_to < effective_from else _months_inclusive(effective_from, effective_to)
    amount = (monthly_exact * months).quantize(CENT, rounding=data.rounding_mode)
    return DepreciationResult(
        monthly_amount=monthly_exact.quantize(CENT, rounding=data.rounding_mode),
        applicable_months=months,
        amount_for_period=min(amount, depreciable.quantize(CENT, rounding=data.rounding_mode)),
        steps=[
            f"Depreciable base: {depreciable}",
            f"Exact monthly amount: {monthly_exact}",
            f"Applicable months: {months}",
        ],
    )


class UtilityAllocationInput(BaseModel):
    total_amount: Decimal
    billing_period_from: date
    billing_period_to: date
    allocation_period_from: date
    allocation_period_to: date
    allocation_basis: str = "days"
    area_ratio: Decimal = Field(default=Decimal("1"), ge=0, le=1)
    occupancy_ratio: Decimal = Field(default=Decimal("1"), ge=0, le=1)

    @model_validator(mode="after")
    def validate_periods(self) -> UtilityAllocationInput:
        if self.billing_period_to < self.billing_period_from:
            raise ValueError("Invalid billing period")
        if self.allocation_period_to < self.allocation_period_from:
            raise ValueError("Invalid allocation period")
        return self


class UtilityAllocationResult(BaseModel):
    total_days: int
    allocated_days: int
    allocation_ratio: Decimal
    allocated_amount: Decimal
    steps: list[str]


def calculate_utility_allocation(data: UtilityAllocationInput) -> UtilityAllocationResult:
    total_days = (data.billing_period_to - data.billing_period_from).days + 1
    overlap_from = max(data.billing_period_from, data.allocation_period_from)
    overlap_to = min(data.billing_period_to, data.allocation_period_to)
    allocated_days = max(0, (overlap_to - overlap_from).days + 1)
    day_ratio = Decimal(allocated_days) / Decimal(total_days)
    ratio = day_ratio * data.area_ratio * data.occupancy_ratio
    amount = (data.total_amount * ratio).quantize(CENT, rounding=ROUND_HALF_UP)
    return UtilityAllocationResult(
        total_days=total_days,
        allocated_days=allocated_days,
        allocation_ratio=ratio.quantize(Decimal("0.00000001"), rounding=ROUND_HALF_UP),
        allocated_amount=amount,
        steps=[
            f"Billing days (inclusive): {total_days}",
            f"Overlapping days (inclusive): {allocated_days}",
            f"Day ratio × area ratio × occupancy ratio: {ratio}",
        ],
    )


def sum_money(values: list[Decimal]) -> Decimal:
    return sum(values, start=Decimal("0")).quantize(CENT, rounding=ROUND_HALF_UP)


def _month_start(value: date) -> date:
    return value.replace(day=1)


def _months_inclusive(start: date, end: date) -> int:
    return (end.year - start.year) * 12 + end.month - start.month + 1


def _add_months(value: date, months: int) -> date:
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    day = min(value.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)
