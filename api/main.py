import sys
import os
import logging
from typing import List

# Add the project root to sys.path to import from src
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from src.application.supply_service import SupplyService
from src.application.demand_service import DemandProjectionService
from src.application.data_source_service import DataSourceService
from src.domain.exceptions import (
    DataLoadError,
    InvalidPolicyError,
    MathInvariantViolation,
)

logger = logging.getLogger(__name__)

app = FastAPI(title="The Spillover Engine API")

# Enable CORS (allow localhost for dev + any origin for containerized deployments)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Application services (shared across endpoints) ---
# NOTE: Services cache loaded data for the lifetime of the process.
# Restart the server after updating data files on disk.
_supply_service = SupplyService()
_demand_service = DemandProjectionService(supply_service=_supply_service)
_data_source_service = DataSourceService()


# --- Exception-to-HTTP mapping ---
def _domain_to_http(exc: Exception) -> HTTPException:
    """Map domain exceptions to appropriate HTTP status codes.

    Sensitive details (file paths, library internals) are logged server-side
    but NOT returned to the client.
    """
    if isinstance(exc, DataLoadError):
        logger.error("Data load error: %s", exc, exc_info=True)
        return HTTPException(status_code=503, detail="Data source unavailable")
    if isinstance(exc, InvalidPolicyError):
        return HTTPException(status_code=422, detail=str(exc))
    if isinstance(exc, MathInvariantViolation):
        logger.error("Math invariant violation: %s", exc, exc_info=True)
        return HTTPException(status_code=500, detail="Internal computation error")
    logger.exception("Unhandled error in endpoint: %s", exc)
    return HTTPException(status_code=500, detail="Internal server error")


# Pydantic response models for clean OpenAPI docs and validation
class WaterfallResponse(BaseModel):
    eb_base_limit: int
    fb_spillover_std: int
    fb_savings_freeze: int
    eb45_spillover_std: int
    eb45_savings_freeze: int
    total_eb_supply: int
    eb1_supply: int
    india_eb1_supply: int


class SupplyDemandResponse(BaseModel):
    inventory: dict
    pipeline_total: int
    total_queue: int
    annual_eb1_supply: int
    monthly_inflow: int
    clearance_date: str
    months_to_clear: int
    cleared: bool
    trajectory: List[dict]


class PredictResponse(BaseModel):
    confidence_score: float
    backlog_ahead: int
    total_queue: int
    annual_eb1_supply: int
    monthly_inflow: int
    target_fy: int
    projected_clearance_date: str
    months_to_clear: int
    cleared: bool
    trajectory: List[dict]


class DataSourceFile(BaseModel):
    filename: str
    parsed_date: str | None = None
    exists: bool = True


class DataSourcesResponse(BaseModel):
    dos_directory: str
    dos_files: List[DataSourceFile]
    inventory_file: DataSourceFile
    pipeline_file: DataSourceFile


@app.get("/api/waterfall", response_model=WaterfallResponse)
async def get_waterfall_data(
    apply_freeze: bool = Query(
        False,
        description="Apply 75-country freeze / Trump Effect (hypothetical full scenario)",
    ),
    apply_real_restrictions: bool = Query(
        False,
        description="Apply actual 2025-2026 Presidential Proclamation country restrictions (real policy, India excluded; ignored if apply_freeze=true for precedence)",
    ),
):
    try:
        breakdown = _supply_service.get_supply_breakdown(
            apply_freeze=apply_freeze,
            apply_real_restrictions=apply_real_restrictions,
        )
        return WaterfallResponse(
            eb_base_limit=breakdown.eb_base_limit,
            fb_spillover_std=breakdown.fb_spillover_std,
            fb_savings_freeze=breakdown.fb_savings_freeze,
            eb45_spillover_std=breakdown.eb45_spillover_std,
            eb45_savings_freeze=breakdown.eb45_savings_freeze,
            total_eb_supply=breakdown.total_eb_supply,
            eb1_supply=breakdown.eb1_supply,
            india_eb1_supply=breakdown.india_eb1_supply,
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise _domain_to_http(exc)


@app.get("/api/supply-demand", response_model=SupplyDemandResponse)
async def get_supply_demand_data(
    apply_freeze: bool = Query(
        False,
        description="Apply 75-country freeze / Trump Effect (hypothetical full scenario)",
    ),
    apply_real_restrictions: bool = Query(
        False,
        description="Apply actual 2025-2026 Presidential Proclamation country restrictions (real policy, India excluded; ignored if apply_freeze=true)",
    ),
):
    try:
        result = _demand_service.project_supply_demand(
            apply_freeze=apply_freeze,
            apply_real_restrictions=apply_real_restrictions,
        )
        return SupplyDemandResponse(**result)
    except HTTPException:
        raise
    except Exception as exc:
        raise _domain_to_http(exc)


@app.get("/api/predict", response_model=PredictResponse)
async def predict_pd(
    priority_date: str = Query(..., description="Priority Date in YYYY-MM-DD format"),
    apply_freeze: bool = Query(
        False,
        description="Apply 75-country freeze / Trump Effect (hypothetical full scenario)",
    ),
    apply_real_restrictions: bool = Query(
        False,
        description="Apply actual 2025-2026 Presidential Proclamation country restrictions (real policy, India excluded; ignored if apply_freeze=true per precedence)",
    ),
):
    try:
        result = _demand_service.predict(
            priority_date,
            apply_freeze=apply_freeze,
            apply_real_restrictions=apply_real_restrictions,
        )
        return PredictResponse(**result)
    except ValueError as exc:
        # Date-validation ValueError from predict(); caught narrowly here
        # so that ValueErrors from deeper in the stack hit the generic 500.
        raise HTTPException(status_code=422, detail=str(exc))
    except HTTPException:
        raise
    except Exception as exc:
        raise _domain_to_http(exc)


@app.get("/api/data-sources", response_model=DataSourcesResponse)
async def get_data_sources():
    """Returns metadata about all currently loaded data files."""
    try:
        result = _data_source_service.get_data_sources()
        return DataSourcesResponse(
            dos_directory=result["dos_directory"],
            dos_files=[DataSourceFile(**f) for f in result["dos_files"]],
            inventory_file=DataSourceFile(**result["inventory_file"]),
            pipeline_file=DataSourceFile(**result["pipeline_file"]),
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise _domain_to_http(exc)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
