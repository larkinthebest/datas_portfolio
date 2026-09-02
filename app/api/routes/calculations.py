from fastapi import APIRouter, Depends

from app.api.dependencies import require_api_key
from app.core.telemetry import CALCULATIONS
from app.domain.calculations import (
    DepreciationInput,
    DepreciationResult,
    UtilityAllocationInput,
    UtilityAllocationResult,
    calculate_linear_depreciation,
    calculate_utility_allocation,
)

router = APIRouter(prefix="/api/v1/calculations", dependencies=[Depends(require_api_key)])


@router.post(
    "/depreciation", response_model=DepreciationResult, summary="Calculate linear depreciation"
)
async def depreciation(data: DepreciationInput) -> DepreciationResult:
    CALCULATIONS.labels(kind="depreciation").inc()
    return calculate_linear_depreciation(data)


@router.post(
    "/utility-allocation",
    response_model=UtilityAllocationResult,
    summary="Allocate utility cost over overlapping periods",
)
async def utility_allocation(data: UtilityAllocationInput) -> UtilityAllocationResult:
    CALCULATIONS.labels(kind="utility_allocation").inc()
    return calculate_utility_allocation(data)
