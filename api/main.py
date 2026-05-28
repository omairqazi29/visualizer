import sys
import os
from datetime import datetime
from typing import List

# Add the project root to sys.path to import from src
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from src.parsers.inventory_parser import InventoryParser
from src.parsers.pipeline_parser import PipelineParser
from src.engine.demand import DemandModeler
from src.engine.supply import SupplyCalculator
from pathlib import Path

from src.data_discovery import (
    get_latest_inventory_path,
    get_latest_pipeline_path,
    get_dos_dir,
    parse_date_from_filename,
)

app = FastAPI(title="The Spillover Engine API")

# Enable CORS (allow localhost for dev + any origin for containerized deployments)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Pydantic response models for clean OpenAPI docs and validation
class WaterfallResponse(BaseModel):
    eb_base_limit: int
    fb_spillover_std: int
    fb_savings_freeze: int
    eb45_spillover_std: int
    eb45_savings_freeze: int
    total_eb_supply: int
    eb1_supply: int
    india_eb1_supply: (
        int  # effective for India after non-India EB-1 usage (or full under freeze)
    )


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
        calc = SupplyCalculator()
        breakdown = calc.get_supply_breakdown(
            apply_freeze=apply_freeze, apply_real_restrictions=apply_real_restrictions
        )
        # NOTE: when apply_real_restrictions, india_eb1_supply is preferentially boosted
        # (see SupplyBreakdown docstring); other aggregates report base for compat.
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
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


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
        # Load inventory + pipeline (demand side) via auto-discovery for drop-in new data
        inv_parser = InventoryParser.latest()
        inv_stats = inv_parser.get_india_eb1_queue()

        pipe_parser = PipelineParser.latest()
        pipe_parser.load_data()
        pipe_total = pipe_parser.get_india_eb1_backlog()

        total_queue = int(inv_stats["total"] + pipe_total)

        # Supply side via centralized calculator
        calc = SupplyCalculator()
        breakdown = calc.get_supply_breakdown(
            apply_freeze=apply_freeze, apply_real_restrictions=apply_real_restrictions
        )
        india_eb1_supply = breakdown.india_eb1_supply

        # Monthly distribution for demand projection
        monthly_dist = calc.dos_parser.get_monthly_distribution(
            country="India", categories=["E11", "E12", "E13"]
        )

        modeler = DemandModeler(total_queue, int(india_eb1_supply), monthly_dist)
        projection = modeler.project_clearance()

        return SupplyDemandResponse(
            inventory={k: int(v) for k, v in inv_stats.items()},
            pipeline_total=int(pipe_total),
            total_queue=int(total_queue),
            annual_eb1_supply=int(india_eb1_supply),
            monthly_inflow=modeler.monthly_inflow,
            clearance_date=projection["clearance_date"].strftime("%Y-%m-%d"),
            months_to_clear=int(projection["months_to_clear"]),
            cleared=projection["cleared"],
            trajectory=projection["trajectory"],
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


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
        try:
            pd_dt = datetime.strptime(priority_date, "%Y-%m-%d")
        except ValueError:
            raise HTTPException(
                status_code=422, detail="priority_date must be in YYYY-MM-DD format"
            )

        # Demand side via auto-discovery (supports new USCIS files without code change)
        inv_parser = InventoryParser.latest()
        inv_stats_total = inv_parser.get_india_eb1_queue()

        pipe_parser = PipelineParser.latest()
        pipe_parser.load_data()
        pipe_total = pipe_parser.get_india_eb1_backlog()

        total_queue = inv_stats_total["total"] + pipe_total

        inv_ahead = inv_parser.get_india_eb1_queue(
            cutoff_month=pd_dt.month, cutoff_year=pd_dt.year
        )

        if pd_dt.year > 2023:
            months_into_pipeline = (pd_dt.year - 2024) * 12 + pd_dt.month
            pipeline_fraction = min(1.0, months_into_pipeline / 24.0)
            backlog_ahead = inv_stats_total["total"] + int(
                pipe_total * pipeline_fraction
            )
        else:
            # Use 'mountain' (PDs strictly before cutoff_year per parser design) for
            # backlog ahead of this PD. Fixes prior use of full 'total' which
            # overstated queue for pre-2024 PDs and reduced prediction accuracy.
            backlog_ahead = inv_ahead.get("mountain", inv_ahead["total"])

        # Supply side via centralized calculator
        calc = SupplyCalculator()
        breakdown = calc.get_supply_breakdown(
            apply_freeze=apply_freeze, apply_real_restrictions=apply_real_restrictions
        )
        india_eb1_supply = breakdown.india_eb1_supply

        monthly_dist = calc.dos_parser.get_monthly_distribution(
            country="India", categories=["E11", "E12", "E13"]
        )

        modeler = DemandModeler(total_queue, int(india_eb1_supply), monthly_dist)
        target_fy = modeler.default_target_fy()
        score = modeler.calculate_confidence_score(
            pd_dt, backlog_ahead=backlog_ahead, target_fy=target_fy
        )
        projection = modeler.project_clearance(backlog=backlog_ahead)

        return PredictResponse(
            confidence_score=float(score),
            backlog_ahead=int(backlog_ahead),
            total_queue=int(total_queue),
            annual_eb1_supply=int(india_eb1_supply),
            monthly_inflow=modeler.monthly_inflow,
            target_fy=target_fy,
            projected_clearance_date=projection["clearance_date"].strftime("%Y-%m-%d"),
            months_to_clear=int(projection["months_to_clear"]),
            cleared=projection["cleared"],
            trajectory=projection["trajectory"],
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/data-sources", response_model=DataSourcesResponse)
async def get_data_sources():
    """Returns metadata about all currently loaded data files."""
    try:
        # DOS directory files
        dos_dir = get_dos_dir()
        dos_path = Path(dos_dir)
        dos_files = []
        if dos_path.is_dir():
            for f in sorted(dos_path.iterdir()):
                if f.suffix == ".xlsx":
                    parsed = parse_date_from_filename(f)
                    date_str = f"{parsed[0]}-{parsed[1]:02d}" if parsed else None
                    dos_files.append(
                        DataSourceFile(filename=f.name, parsed_date=date_str)
                    )

        # Inventory file
        inv_path_str = get_latest_inventory_path()
        inv_path = Path(inv_path_str)
        inv_parsed = parse_date_from_filename(inv_path)
        inv_date = f"{inv_parsed[0]}-{inv_parsed[1]:02d}" if inv_parsed else None
        inv_file = DataSourceFile(
            filename=inv_path.name, parsed_date=inv_date, exists=inv_path.exists()
        )

        # Pipeline file
        pipe_path_str = get_latest_pipeline_path()
        pipe_path = Path(pipe_path_str)
        pipe_parsed = parse_date_from_filename(pipe_path)
        pipe_date = f"{pipe_parsed[0]}-{pipe_parsed[1]:02d}" if pipe_parsed else None
        pipe_file = DataSourceFile(
            filename=pipe_path.name, parsed_date=pipe_date, exists=pipe_path.exists()
        )

        return DataSourcesResponse(
            dos_directory=dos_dir,
            dos_files=dos_files,
            inventory_file=inv_file,
            pipeline_file=pipe_file,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
