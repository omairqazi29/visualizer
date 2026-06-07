import sys
import os
from datetime import datetime, timedelta
from typing import List

# Add the project root to sys.path to import from src
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from src.parsers.inventory_parser import InventoryParser
from src.parsers.pipeline_parser import PipelineParser
from src.parsers.visa_bulletin_parser import VisaBulletinParser
from src.parsers.nvc_parser import NVCParser
from src.parsers.i485_parser import I485FlowParser
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
    nvc_backlog: dict | None = None  # NVC consular processing pipeline
    total_queue: int
    annual_eb1_supply: int
    supply_by_fy: dict[str, int]  # {fy_year: india_eb1_supply}
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
    # DOF estimate (data-driven from VB history)
    dof_estimate_date: str | None = None
    dof_lead_months: float = 0
    dof_range_min: float = 0
    dof_range_max: float = 0
    dof_datapoints: int = 0
    # Current VB status (actual, not estimated)
    vb_bulletin_month: str | None = None
    vb_current_fad: str | None = None
    vb_current_dof: str | None = None
    vb_fad_is_current: bool = False
    vb_dof_is_current: bool = False
    vb_fad_remaining_months: float = 0
    vb_dof_remaining_months: float = 0


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

        # Per-FY supply schedule
        fy_supply = calc.get_supply_by_fy(
            apply_freeze=apply_freeze, apply_real_restrictions=apply_real_restrictions
        )

        # NVC backlog (consular processing pipeline — disjoint from I-485 AOS)
        nvc_data = None
        try:
            nvc = NVCParser()
            india_nvc = nvc.get_india_eb_nvc()
            nvc_data = {
                "report_date": nvc.get_latest_report_date(),
                "india_eb1_nvc": india_nvc.get("EB1", 0),
                "india_eb_total": sum(india_nvc.values()),
                "worldwide_eb_total": nvc.get_eb_total_worldwide(),
                "india_by_category": india_nvc,
            }
        except Exception:
            pass

        modeler = DemandModeler(total_queue, monthly_distribution=monthly_dist, fy_supply=fy_supply)
        projection = modeler.project_clearance()

        return SupplyDemandResponse(
            inventory={k: int(v) for k, v in inv_stats.items()},
            pipeline_total=int(pipe_total),
            nvc_backlog=nvc_data,
            total_queue=int(total_queue),
            annual_eb1_supply=int(modeler.default_supply),
            supply_by_fy={str(k): v for k, v in fy_supply.items()},
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

        # Supply side via centralized calculator (per-FY schedule)
        calc = SupplyCalculator()
        monthly_dist = calc.dos_parser.get_monthly_distribution(
            country="India", categories=["E11", "E12", "E13"]
        )
        fy_supply = calc.get_supply_by_fy(
            apply_freeze=apply_freeze, apply_real_restrictions=apply_real_restrictions
        )

        modeler = DemandModeler(total_queue, monthly_distribution=monthly_dist, fy_supply=fy_supply)
        india_eb1_supply = modeler.default_supply
        score = modeler.calculate_confidence_score(
            pd_dt, backlog_ahead=backlog_ahead, target_fy=2027
        )
        projection = modeler.project_clearance(backlog=backlog_ahead)

        # DOF estimate + current VB status from historical data
        vb_status = {}
        try:
            vb = VisaBulletinParser()
            dof_lead = vb.get_dof_lead_months(recent_n=12)
            gap = dof_lead["median_gap"]
            clearance = projection["clearance_date"]
            dof_est = clearance - timedelta(days=int(gap * 30.44))
            dof_est_str = dof_est.strftime("%Y-%m-%d")
            vb_status = vb.get_current_status(priority_date)
        except Exception:
            dof_lead = {"median_gap": 0, "min_gap": 0, "max_gap": 0, "n_datapoints": 0}
            dof_est_str = None

        return PredictResponse(
            confidence_score=float(score),
            backlog_ahead=int(backlog_ahead),
            total_queue=int(total_queue),
            annual_eb1_supply=int(india_eb1_supply),
            projected_clearance_date=projection["clearance_date"].strftime("%Y-%m-%d"),
            months_to_clear=int(projection["months_to_clear"]),
            trajectory=projection["trajectory"],
            dof_estimate_date=dof_est_str,
            dof_lead_months=dof_lead["median_gap"],
            dof_range_min=dof_lead["min_gap"],
            dof_range_max=dof_lead["max_gap"],
            dof_datapoints=dof_lead["n_datapoints"],
            vb_bulletin_month=vb_status.get("bulletin_month"),
            vb_current_fad=vb_status.get("current_fad"),
            vb_current_dof=vb_status.get("current_dof"),
            vb_fad_is_current=vb_status.get("fad_is_current", False),
            vb_dof_is_current=vb_status.get("dof_is_current", False),
            vb_fad_remaining_months=vb_status.get("fad_remaining_months", 0),
            vb_dof_remaining_months=vb_status.get("dof_remaining_months", 0),
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class InventoryContextResponse(BaseModel):
    """Full demand-side context from USCIS inventory + pipeline + NVC data."""
    eb1_backlogs: dict[str, int]            # EB-1 I-485 pending by country (with dependents)
    india_all_eb_backlogs: dict[str, int]   # India all EB categories I-485 pending
    pipeline: dict[str, dict[str, int]]     # I-140 pipeline by country and category
    nvc_backlog: dict | None = None         # NVC consular processing pipeline
    india_oversubscribed_share: float       # Computed share from inventory data
    inventory_date: str                     # "January 2026"
    pipeline_date: str                      # "September 2025"
    nvc_report_date: str | None = None      # "November 2023"


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

        # NVC backlog (consular processing pipeline)
        nvc_data = None
        nvc_date = None
        try:
            nvc = NVCParser()
            nvc_summary = nvc.get_summary()
            nvc_data = {
                "eb_totals_by_category": nvc_summary["eb_totals_by_category"],
                "eb_total_worldwide": nvc_summary["eb_total_worldwide"],
                "eb_by_country": nvc_summary["eb_by_country"],
                "india_eb_by_category": nvc_summary["india_eb_by_category"],
                "india_eb_total": nvc_summary["india_eb_total"],
                "india_eb1_nvc": nvc_summary["india_eb1_nvc"],
                "iv_backlog": nvc_summary["iv_backlog"],
                "notes": nvc_summary["notes"],
            }
            nvc_date = nvc_summary["report_date"]
        except Exception:
            pass

        return InventoryContextResponse(
            eb1_backlogs=eb1_backlogs,
            india_all_eb_backlogs=india_all,
            pipeline=pipeline,
            nvc_backlog=nvc_data,
            india_oversubscribed_share=round(india_share, 4),
            inventory_date="February 2026",
            pipeline_date="September 2025",
            nvc_report_date=nvc_date,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class NVCBacklogResponse(BaseModel):
    """NVC (National Visa Center) backlog data — consular processing pipeline."""
    report_date: str
    eb_totals_by_category: dict[str, int]
    eb_total_worldwide: int
    eb_by_country: dict[str, int]
    india_eb_by_category: dict[str, int]
    india_eb_total: int
    india_eb1_nvc: int
    iv_backlog: dict | None = None
    yoy_comparison: dict[str, dict[str, int]] | None = None
    notes: dict


@app.get("/api/nvc-backlog", response_model=NVCBacklogResponse)
async def get_nvc_backlog():
    """Returns NVC backlog data — the hidden pipeline stage between I-140 approval
    and consular interview.

    This captures consular processing (CP) cases registered at the National Visa Center.
    These are DISJOINT from I-485 inventory (AOS path). Together they represent
    the complete demand picture. ~85% of EB immigrants go AOS; ~15% go CP via NVC.

    Data source: DOS ARIVA (Annual Report of IV Applicants at the NVC).
    """
    try:
        nvc = NVCParser()
        summary = nvc.get_summary()
        yoy = nvc.get_yoy_comparison()

        return NVCBacklogResponse(
            report_date=summary["report_date"],
            eb_totals_by_category=summary["eb_totals_by_category"],
            eb_total_worldwide=summary["eb_total_worldwide"],
            eb_by_country=summary["eb_by_country"],
            india_eb_by_category=summary["india_eb_by_category"],
            india_eb_total=summary["india_eb_total"],
            india_eb1_nvc=summary["india_eb1_nvc"],
            iv_backlog=summary["iv_backlog"],
            yoy_comparison=yoy,
            notes=summary["notes"],
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class I485FlowPoint(BaseModel):
    period: str
    year: int
    month: int
    source: str  # "monthly" or "quarterly"
    months_covered: int
    eb_receipts: int
    eb_approvals: int
    eb_denials: int
    eb_pending: int
    fb_receipts: int
    fb_approvals: int
    total_receipts: int
    total_approvals: int
    total_denials: int
    total_pending: int
    eb_net_flow: int
    total_net_flow: int


class I485FlowResponse(BaseModel):
    monthly: list[I485FlowPoint]
    quarterly: list[I485FlowPoint]
    summary: dict


@app.get("/api/i485-flow", response_model=I485FlowResponse)
async def get_i485_flow():
    """Returns monthly I-485 receipts vs. approvals data.

    Shows inflow rate (new demand) vs. outflow (approvals) to model
    whether the I-485 queue is growing or shrinking.

    Data sources: USCIS monthly Congressional reports (CSV) and quarterly
    I-485 performance data (XLSX) from data/USCIS_I485/.
    """
    try:
        parser = I485FlowParser()
        monthly_raw = parser.get_monthly_series()
        quarterly_raw = parser.get_quarterly_series()
        summary = parser.get_eb_summary()

        # Strip 'categories' (detailed breakdown) from API response points
        monthly = [
            I485FlowPoint(**{k: v for k, v in d.items() if k in I485FlowPoint.model_fields})
            for d in monthly_raw
        ]
        quarterly = [
            I485FlowPoint(**{k: v for k, v in d.items() if k in I485FlowPoint.model_fields})
            for d in quarterly_raw
        ]

        return I485FlowResponse(
            monthly=monthly,
            quarterly=quarterly,
            summary=summary,
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
        dependent_multiplier=2.5,
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
            {
                "name": "NVC Waiting List (ARIVA)",
                "description": "Annual Report of IV Applicants Registered at the NVC — consular processing pipeline (disjoint from I-485 AOS). Includes derivatives.",
                "url": "https://travel.state.gov/content/dam/visas/Statistics/Immigrant-Statistics/WaitingList/WaitingListItem_2023_vF.pdf",
                "coverage": "November 2023",
                "update_frequency": "Annual",
            },
            {
                "name": "USCIS I-485 Performance Data",
                "description": "Monthly receipts, approvals, denials, and pending counts for I-485 by category",
                "url": "https://www.uscis.gov/tools/reports-and-studies/immigration-and-citizenship-data",
                "coverage": "Jul 2024 – Feb 2026 (monthly) + FY2024–FY2025 (quarterly)",
                "update_frequency": "Monthly (Congressional mandate)",
            },
            {
                "name": "NVC IV Backlog Report",
                "description": "Monthly report of documentarily complete cases ready for consular interview scheduling",
                "url": "https://travel.state.gov/content/dam/visas/iv-backlog-report/IV%20Report%20-%20September%202024.pdf",
                "coverage": "September 2024",
                "update_frequency": "Monthly (discontinued after Sep 2024)",
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


class VBHistoryRow(BaseModel):
    bulletin_month: str
    category: str
    fad: str | None
    dof: str | None


class VBHistoryResponse(BaseModel):
    categories: List[str]
    total_rows: int
    history: List[VBHistoryRow]


@app.get("/api/visa-bulletin-history", response_model=VBHistoryResponse)
async def get_visa_bulletin_history(
    category: str = Query(
        None,
        description="Filter by EB category (EB-1, EB-2, EB-3). Returns all if omitted.",
    ),
    country: str = Query(
        "India",
        description="Country to query (India, China). Defaults to India.",
    ),
):
    """Returns historical Visa Bulletin FAD/DOF data for India EB categories.

    Supports cross-category comparison for EB-1, EB-2, and EB-3.
    """
    try:
        vb = VisaBulletinParser(country=country)
        if category:
            rows = vb.get_history(category=category)
        else:
            rows = vb.get_all_categories_history()

        history = []
        for r in rows:
            history.append(VBHistoryRow(
                bulletin_month=r["bulletin_month"],
                category=r["category"],
                fad=r["fad"].isoformat() if r["fad"] else None,
                dof=r["dof"].isoformat() if r["dof"] else None,
            ))

        categories = sorted(set(r.category for r in history))
        return VBHistoryResponse(
            categories=categories,
            total_rows=len(history),
            history=history,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
