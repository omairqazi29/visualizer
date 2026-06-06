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
from src.constants import ACTUAL_RESTRICTED_COUNTRIES, DEFAULT_INDIA_EB1_SUPPLY, FB_STATUTORY_LIMIT

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
    # Full INA cascade
    eb_base_limit: int
    fb_spillover: int
    total_eb_pool: int
    eb1_from_pool: int
    eb45_spillover: int
    total_eb1: int
    # India EB-1
    india_eb1_baseline: int
    india_eb1_supply: int
    non_india_eb1: int
    # Savings breakdown
    fb_savings: int
    eb1_savings: int
    eb45_savings: int
    eb23_savings: int
    # Data-driven share
    india_oversubscribed_share: float


class SupplyDemandResponse(BaseModel):
    inventory: dict
    pipeline_total: int
    total_queue: int
    annual_eb1_supply: int
    clearance_date: str
    months_to_clear: int
    trajectory: List[dict]


class PredictResponse(BaseModel):
    confidence_score: float
    backlog_ahead: int
    total_queue: int
    annual_eb1_supply: int
    projected_clearance_date: str
    months_to_clear: int
    trajectory: List[dict]


@app.get("/api/waterfall", response_model=WaterfallResponse)
async def get_waterfall_data(
    apply_freeze: bool = Query(
        False,
        description="Apply maximum hypothetical freeze on top-consuming countries (Philippines, Mexico, etc.) beyond real restrictions",
    ),
    apply_real_restrictions: bool = Query(
        False,
        description="Apply real 2025-2026 restrictions: 39-country Proclamation ban + 75-country DOS IV pause (91 countries total; India excluded; ignored if apply_freeze=true)",
    ),
):
    try:
        calc = SupplyCalculator()
        breakdown = calc.get_supply_breakdown(
            apply_freeze=apply_freeze, apply_real_restrictions=apply_real_restrictions
        )
        return WaterfallResponse(
            eb_base_limit=breakdown.eb_base_limit,
            fb_spillover=breakdown.fb_spillover,
            total_eb_pool=breakdown.total_eb_pool,
            eb1_from_pool=breakdown.eb1_from_pool,
            eb45_spillover=breakdown.eb45_spillover,
            total_eb1=breakdown.total_eb1,
            india_eb1_baseline=breakdown.india_eb1_baseline,
            india_eb1_supply=breakdown.india_eb1_supply,
            non_india_eb1=breakdown.non_india_eb1,
            fb_savings=breakdown.fb_savings,
            eb1_savings=breakdown.eb1_savings,
            eb45_savings=breakdown.eb45_savings,
            eb23_savings=breakdown.eb23_savings,
            india_oversubscribed_share=breakdown.india_oversubscribed_share,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/supply-demand", response_model=SupplyDemandResponse)
async def get_supply_demand_data(
    apply_freeze: bool = Query(
        False,
        description="Apply maximum hypothetical freeze on top-consuming countries beyond real restrictions",
    ),
    apply_real_restrictions: bool = Query(
        False,
        description="Apply real 2025-2026 restrictions: 91 countries (Proclamation ban + DOS IV pause; India excluded; ignored if apply_freeze=true)",
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
            clearance_date=projection["clearance_date"].strftime("%Y-%m-%d"),
            months_to_clear=int(projection["months_to_clear"]),
            trajectory=projection["trajectory"],
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/predict", response_model=PredictResponse)
async def predict_pd(
    priority_date: str = Query(..., description="Priority Date in YYYY-MM-DD format"),
    apply_freeze: bool = Query(
        False,
        description="Apply maximum hypothetical freeze on top-consuming countries beyond real restrictions",
    ),
    apply_real_restrictions: bool = Query(
        False,
        description="Apply real 2025-2026 restrictions: 91 countries (Proclamation ban + DOS IV pause; India excluded; ignored if apply_freeze=true)",
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
        score = modeler.calculate_confidence_score(
            pd_dt, backlog_ahead=backlog_ahead, target_fy=2027
        )
        projection = modeler.project_clearance(backlog=backlog_ahead)

        return PredictResponse(
            confidence_score=float(score),
            backlog_ahead=int(backlog_ahead),
            total_queue=int(total_queue),
            annual_eb1_supply=int(india_eb1_supply),
            projected_clearance_date=projection["clearance_date"].strftime("%Y-%m-%d"),
            months_to_clear=int(projection["months_to_clear"]),
            trajectory=projection["trajectory"],
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class InventoryContextResponse(BaseModel):
    """Full demand-side context from USCIS inventory + pipeline data."""
    eb1_backlogs: dict[str, int]            # EB-1 I-485 pending by country (with dependents)
    india_all_eb_backlogs: dict[str, int]   # India all EB categories I-485 pending
    pipeline: dict[str, dict[str, int]]     # I-140 pipeline by country and category
    india_oversubscribed_share: float       # Computed share from inventory data
    inventory_date: str                     # "January 2026"
    pipeline_date: str                      # "September 2025"


@app.get("/api/inventory-context", response_model=InventoryContextResponse)
async def get_inventory_context():
    """Returns full demand-side data from USCIS inventory and pipeline files.

    Shows all EB backlogs by country (not just India EB-1), the I-140 pipeline,
    and the data-driven India oversubscribed share computation.
    """
    try:
        inv = InventoryParser.latest()
        eb1_backlogs = inv.get_all_eb1_backlogs()

        all_eb = inv.get_all_eb_backlogs()
        india_all = all_eb.get("India", {})

        pipe = PipelineParser.latest()
        pipe.load_data()
        pipeline = pipe.get_all_eb_pipeline()

        india_share = SupplyCalculator.compute_india_share()

        return InventoryContextResponse(
            eb1_backlogs=eb1_backlogs,
            india_all_eb_backlogs=india_all,
            pipeline=pipeline,
            india_oversubscribed_share=round(india_share, 4),
            inventory_date="February 2026",
            pipeline_date="September 2025",
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class MethodologyResponse(BaseModel):
    restricted_countries: List[str]
    restricted_countries_count: int
    india_eb1_baseline: int
    eb_base_limit: int
    fb_statutory_limit: int
    dependent_multiplier: float
    data_sources: List[dict]
    legal_status: List[dict]
    last_verified: str


@app.get("/api/methodology", response_model=MethodologyResponse)
async def get_methodology():
    """Returns model parameters, data sources, and legal status for transparency."""
    return MethodologyResponse(
        restricted_countries=sorted(ACTUAL_RESTRICTED_COUNTRIES),
        restricted_countries_count=len(ACTUAL_RESTRICTED_COUNTRIES),
        india_eb1_baseline=DEFAULT_INDIA_EB1_SUPPLY,
        eb_base_limit=140000,
        fb_statutory_limit=226000,
        dependent_multiplier=2.2,
        data_sources=[
            {
                "name": "DOS Monthly IV Issuances",
                "description": "Consular immigrant visa issuances by country and category",
                "url": "https://travel.state.gov/content/travel/en/legal/visa-law0/visa-statistics.html",
                "coverage": "FY2025 (Oct 2024 - Sep 2025)",
                "update_frequency": "Monthly (~2-3 month lag)",
            },
            {
                "name": "USCIS EB I-485 Inventory",
                "description": "Pending adjustment of status cases by country, category, PD year",
                "url": "https://www.uscis.gov/tools/reports-and-studies",
                "coverage": "February 2026",
                "update_frequency": "Quarterly",
            },
            {
                "name": "USCIS I-140 Performance Data",
                "description": "Approved I-140 petitions awaiting visa numbers (pipeline)",
                "url": "https://www.uscis.gov/tools/reports-and-studies",
                "coverage": "FY2025 Q4",
                "update_frequency": "Quarterly",
            },
            {
                "name": "Report of the Visa Office (FY2024)",
                "description": "Annual India EB-1 issuances baseline (6,952 of 47,462 total)",
                "url": "https://travel.state.gov/content/travel/en/legal/visa-law0/visa-statistics.html",
                "coverage": "FY2024",
                "update_frequency": "Annual",
            },
        ],
        legal_status=[
            {
                "policy": "Presidential Proclamations 10949/10998",
                "description": "Suspend immigrant visa entry for 39 countries (security/vetting)",
                "status": "In effect",
                "model_impact": "Part of ACTUAL_RESTRICTED_COUNTRIES union (91 total). Zeroes consular IV usage from listed countries to compute spillover savings from DOS data.",
            },
            {
                "policy": "DOS 75-Country IV Pause (Public Charge)",
                "description": "Pauses consular immigrant visa issuance for 75 countries at high risk of public benefits reliance (eff. Jan 21, 2026)",
                "status": "In effect — lawsuit pending (CLINIC v. Rubio, S.D.N.Y.)",
                "model_impact": "Part of ACTUAL_RESTRICTED_COUNTRIES union (91 total). Directly halts consular IV issuances — the exact data source the model measures. Adds major countries: Brazil, Pakistan, Bangladesh, Egypt, Ethiopia, Colombia, Ghana, Iraq, etc.",
            },
            {
                "policy": "USCIS Adjudicative Hold (PM-602-0192/0194)",
                "description": "Paused domestic I-485/benefit processing for 39 Proclamation countries",
                "status": "Vacated nationwide — Dorcas v. USCIS (Jun 5, 2026)",
                "model_impact": "None. Model uses DOS consular IV data (ground truth). Ruling affects USCIS domestic processing, a separate pathway not measured by DOS.",
            },
        ],
        last_verified="2026-06",
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
