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
from src.parsers.processing_times_parser import ProcessingTimesParser
from src.engine.demand import DemandModeler
from src.engine.legislation import PENDING_BILLS, compute_legislation_scenarios
from src.engine.supply import SupplyCalculator
from src.parsers.dhs_yearbook_parser import DhsYearbookParser
from src.parsers.perm_parser import PERMParser
from src.parsers.h1b_parser import H1BParser
from src.parsers.ceac_parser import CEACParser
from src.parsers.i140_receipts_parser import I140ReceiptsParser
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
    # Per-country savings breakdown (empty dicts under baseline)
    fb_savings_by_country: dict[str, int]
    eb1_savings_by_country: dict[str, int]
    eb45_savings_by_country: dict[str, int]
    eb23_savings_by_country: dict[str, int]
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
            fb_savings_by_country=breakdown.fb_savings_by_country,
            eb1_savings_by_country=breakdown.eb1_savings_by_country,
            eb45_savings_by_country=breakdown.eb45_savings_by_country,
            eb23_savings_by_country=breakdown.eb23_savings_by_country,
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


class ProcessingTimePoint(BaseModel):
    publication_date: str
    office_code: str
    office_name: str
    form_type: str
    category: str
    processing_time_min_months: float
    processing_time_max_months: float
    receipt_date_for_inquiry: str


class ProcessingTimesCategoryBreakdown(BaseModel):
    avg_min_months: float
    avg_max_months: float
    avg_midpoint_months: float
    avg_spread_months: float
    centers_count: int
    fastest_center: str
    slowest_center: str


class ProcessingTimesResponse(BaseModel):
    time_series: list[ProcessingTimePoint]
    latest: list[ProcessingTimePoint]
    summary: dict


@app.get("/api/processing-times", response_model=ProcessingTimesResponse)
async def get_processing_times(
    category: str = Query(
        None,
        description="Filter by EB category (EB-1, EB-2, EB-3). Returns all if omitted.",
    ),
    office_code: str = Query(
        None,
        description="Filter by service center code (NSC, TSC, NBC, PSC). Returns all if omitted.",
    ),
):
    """Returns USCIS processing times by service center for EB I-485.

    Shows how fast each service center (Nebraska, Texas, NBC, Potomac) is
    actually adjudicating EB I-485s. Reveals domestic processing bottlenecks
    that affect how quickly approved visa numbers turn into green cards.

    Data source: USCIS Processing Times page (egov.uscis.gov/processing-times/).
    Published monthly.
    """
    try:
        parser = ProcessingTimesParser()
        time_series = parser.get_time_series(category=category, office_code=office_code)
        latest = parser.get_latest()
        if category:
            latest = [r for r in latest if r["category"] == category]
        if office_code:
            latest = [r for r in latest if r["office_code"] == office_code]
        summary = parser.get_bottleneck_summary()

        return ProcessingTimesResponse(
            time_series=[ProcessingTimePoint(**{k: v for k, v in r.items() if k in ProcessingTimePoint.model_fields}) for r in time_series],
            latest=[ProcessingTimePoint(**{k: v for k, v in r.items() if k in ProcessingTimePoint.model_fields}) for r in latest],
            summary=summary,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class PERMFYData(BaseModel):
    fiscal_year: int
    total: int
    india: int
    china: int
    row: int
    has_country_data: bool


class PERMCategoryData(BaseModel):
    fiscal_year: int
    eb2: int
    eb3: int
    unknown: int
    total: int


class PERMIndiaPipeline(BaseModel):
    fiscal_year: int
    eb2: int
    eb3: int
    unknown: int
    total: int


class PERMStatusData(BaseModel):
    fiscal_year: int
    certified: int
    certified_expired: int
    denied: int
    withdrawn: int
    other: int
    total: int
    approval_rate: float


class PERMTopCountry(BaseModel):
    country: str
    total: int
    pct: float


class PERMPipelineResponse(BaseModel):
    """DOL PERM Labor Certification pipeline — leading indicator of EB-2/EB-3 I-140 filings."""
    by_fy: list[PERMFYData]
    by_category: list[PERMCategoryData]
    india_pipeline: list[PERMIndiaPipeline]
    status_breakdown: list[PERMStatusData]
    top_countries: list[PERMTopCountry]
    summary: dict


@app.get("/api/perm-pipeline", response_model=PERMPipelineResponse)
async def get_perm_pipeline():
    """Returns DOL PERM Labor Certification data — the upstream pipeline that
    feeds into EB-2/EB-3 I-140 filings.

    Each certified PERM is a ~12-24 month leading indicator of a future I-140
    petition. By tracking PERM certifications by country and inferred EB category,
    this models the "pipeline of future demand" entering the EB system.

    Data source: DOL OFLC Performance Data (quarterly disclosure files).
    """
    try:
        parser = PERMParser()
        return PERMPipelineResponse(
            by_fy=[PERMFYData(**d) for d in parser.get_certified_by_fy()],
            by_category=[PERMCategoryData(**d) for d in parser.get_certified_by_category()],
            india_pipeline=[PERMIndiaPipeline(**d) for d in parser.get_india_pipeline()],
            status_breakdown=[PERMStatusData(**d) for d in parser.get_status_breakdown()],
            top_countries=[PERMTopCountry(**d) for d in parser.get_top_countries()],
            summary=parser.get_summary(),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class H1BCapRegistration(BaseModel):
    fiscal_year: int
    total_registrations: int
    eligible_registrations: int
    unique_beneficiaries: int
    multiple_registrations: int
    selected_registrations: int
    selection_rate: float
    multiple_reg_pct: float


class H1BApprovalByCountry(BaseModel):
    fiscal_year: int
    country_of_birth: str
    approvals: int
    initial_approvals: int
    continuing_approvals: int
    share_pct: float


class H1BIndiaDemand(BaseModel):
    fiscal_year: int
    india_approvals: int
    india_initial: int
    india_continuing: int
    india_share_pct: float
    total_approvals: int
    selected_registrations: int | None = None
    selection_rate: float | None = None
    total_registrations: int | None = None
    unique_beneficiaries: int | None = None


class H1BTopCountry(BaseModel):
    country: str
    approvals: int
    share_pct: float


class H1BDemandResponse(BaseModel):
    """H-1B cap registration and approval data — future demand pressure indicator."""
    cap_registrations: list[H1BCapRegistration]
    india_demand: list[H1BIndiaDemand]
    top_countries: list[H1BTopCountry]
    summary: dict


@app.get("/api/h1b-demand", response_model=H1BDemandResponse)
async def get_h1b_demand():
    """Returns H-1B cap registration and approval data — a leading indicator
    of future I-140 filings and EB demand pressure.

    Most India EB-1/2/3 cases flow through H-1B first. Cap registrations show
    demand volume vs. available slots, while approval country-of-birth shares
    show India's dominant position (~70%) in the H-1B pipeline.

    Data sources:
    - USCIS H-1B Electronic Registration Process (cap registrations, FY2021+)
    - USCIS Characteristics of H-1B Specialty Occupation Workers (annual reports)
    """
    try:
        parser = H1BParser()
        return H1BDemandResponse(
            cap_registrations=[H1BCapRegistration(**d) for d in parser.get_cap_registrations()],
            india_demand=[H1BIndiaDemand(**d) for d in parser.get_india_demand_pressure()],
            top_countries=[H1BTopCountry(**d) for d in parser.get_top_countries()],
            summary=parser.get_summary(),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class LegislationBillModel(BaseModel):
    """Schema for a single pending legislation bill."""
    id: str
    bill_number: str
    title: str
    short_title: str
    sponsor: str
    introduced: str
    status: str
    status_detail: str
    chamber: str
    direction: str
    likelihood: str
    categories_affected: List[str]
    scenario_id: str | None = None
    key_provisions: List[str]
    impact_summary: str


class LegislationResponse(BaseModel):
    """Pending legislation bills and what-if scenario projections."""
    bills: List[LegislationBillModel]
    scenarios: dict
    baseline: dict
    last_updated: str


@app.get("/api/legislation", response_model=LegislationResponse)
async def get_legislation():
    """Returns pending legislation data and what-if scenario projections.

    Models how proposed immigration bills in the 119th Congress would affect
    India EB-1 backlog clearance timelines.  Each bill's key provisions are
    translated into supply/demand modifications and projected through the
    DemandModeler.

    Returns both the bills metadata (sponsors, status, provisions) and
    computed scenario projections (clearance date, delta months, trajectory).
    """
    try:
        # --- Demand side (same as /supply-demand) ---
        inv_parser = InventoryParser.latest()
        inv_stats = inv_parser.get_india_eb1_queue()

        pipe_parser = PipelineParser.latest()
        pipe_parser.load_data()
        pipe_total = pipe_parser.get_india_eb1_backlog()

        total_queue = int(inv_stats["total"] + pipe_total)

        # --- Supply side ---
        calc = SupplyCalculator()
        breakdown = calc.get_supply_breakdown()
        baseline_supply = breakdown.india_eb1_supply

        monthly_dist = calc.dos_parser.get_monthly_distribution(
            country="India", categories=["E11", "E12", "E13"]
        )
        fy_supply = calc.get_supply_by_fy()

        # --- Compute legislation scenarios ---
        result = compute_legislation_scenarios(
            inventory_total=total_queue,
            baseline_supply=baseline_supply,
            fy_supply=fy_supply,
            monthly_distribution=monthly_dist,
        )

        return LegislationResponse(
            bills=PENDING_BILLS,
            scenarios=result["scenarios"],
            baseline=result["baseline"],
            last_updated="2026-06-01",
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class CEACIssuancePoint(BaseModel):
    month: str
    eb1_issuances: int
    eb1_principal: int


class CEACPostSummary(BaseModel):
    post: str
    post_name: str
    total_eb1: int
    total_principal: int
    months_active: int


class CEACFYData(BaseModel):
    fiscal_year: int
    total_eb1: int
    principal_eb1: int
    india_eb1: int
    india_principal: int


class CEACNVCWaitPoint(BaseModel):
    date: str
    days: int


class CEACSchedulingResponse(BaseModel):
    """CEAC consular interview scheduling data — real-time consular pipeline activity."""
    india_monthly: list[CEACIssuancePoint]
    fiscal_year_data: list[CEACFYData]
    top_posts: list[CEACPostSummary]
    nvc_wait_times: dict[str, list[CEACNVCWaitPoint]]
    nvc_latest: dict[str, int]
    data_range: dict
    summary: dict


@app.get("/api/ceac-scheduling", response_model=CEACSchedulingResponse)
async def get_ceac_scheduling():
    """Returns CEAC consular interview scheduling and issuance data.

    Shows real-time consular pipeline activity scraped from DOS consulate data.
    Validates DOS IV issuance projections by providing ground-truth
    consulate-level issuance counts and backlog estimates.

    Includes:
    - India EB-1 monthly issuances across all 5 Indian consulates
    - Global EB-1 issuances by fiscal year (for cross-referencing with DOS data)
    - Top consulates by EB-1 issuance volume
    - NVC case processing wait times (creation, review, inquiry queues)

    Data source: visawhen.com (GitHub: underyx/visawhen) — automated scraper
    pulling consulate-level data from DOS.
    """
    try:
        parser = CEACParser()

        india_monthly = parser.get_india_eb1_monthly_total()
        fy_data = parser.get_global_eb1_by_fiscal_year()
        top_posts = parser.get_top_posts_by_eb1(top_n=15)
        nvc_wt = parser.get_nvc_wait_times()
        nvc_latest = parser.get_nvc_latest()
        data_range = parser.get_data_range()
        summary = parser.get_summary()

        return CEACSchedulingResponse(
            india_monthly=[CEACIssuancePoint(**d) for d in india_monthly],
            fiscal_year_data=[CEACFYData(**d) for d in fy_data],
            top_posts=[CEACPostSummary(**d) for d in top_posts],
            nvc_wait_times={
                k: [CEACNVCWaitPoint(**p) for p in v]
                for k, v in nvc_wt.items()
            },
            nvc_latest=nvc_latest,
            data_range=data_range,
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
        dependent_multiplier=DhsYearbookParser().get_latest_multipliers().get("EB1", 2.5),
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
                "name": "USCIS I-140 Receipts (New Filings)",
                "description": "New I-140 petitions filed by country and EB category. Models queue growth rate — how fast new EB petitions enter the system. Separate from approved/pipeline data.",
                "url": "https://www.uscis.gov/tools/reports-and-studies/immigration-and-citizenship-data",
                "coverage": "FY2014–FY2025 (Q1-Q4)",
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
                "name": "USCIS Processing Times by Service Center",
                "description": "Monthly processing times for EB I-485 at each service center (Nebraska, Texas, NBC, Potomac). Shows domestic adjudication bottlenecks.",
                "url": "https://egov.uscis.gov/processing-times/",
                "coverage": "Jan 2024 – May 2025",
                "update_frequency": "Monthly",
            },
            {
                "name": "DHS Yearbook Table 7 (EB Multipliers)",
                "description": "Persons Obtaining LPR Status by Type and Detailed Class of Admission — used to compute principal-to-total multipliers per EB category",
                "url": "https://ohss.dhs.gov/topics/immigration/yearbook",
                "coverage": "FY2015–FY2023",
                "update_frequency": "Annual (released ~9 months after FY end)",
            },
            {
                "name": "DOL PERM Labor Certification Data",
                "description": "PERM disclosure data — certified labor certifications as a leading indicator of future EB-2/EB-3 I-140 filings. Includes country of citizenship and education level for EB category inference.",
                "url": "https://www.dol.gov/agencies/eta/foreign-labor/performance",
                "coverage": "FY2023–FY2026 Q2",
                "update_frequency": "Quarterly",
            },
            {
                "name": "USCIS H-1B Cap Registration & Approval Data",
                "description": "H-1B cap registrations, selections, and approvals by country of birth. Leading indicator of future I-140 filings — most India EB-1/2/3 flow through H-1B first.",
                "url": "https://www.uscis.gov/working-in-the-united-states/temporary-workers/h-1b-specialty-occupations/h-1b-electronic-registration-process",
                "coverage": "FY2019–FY2026 (registrations from FY2021; approvals FY2019+)",
                "update_frequency": "Annual (Characteristics Report ~6 months after FY end)",
            },
            {
                "name": "NVC IV Backlog Report",
                "description": "Monthly report of documentarily complete cases ready for consular interview scheduling",
                "url": "https://travel.state.gov/content/dam/visas/iv-backlog-report/IV%20Report%20-%20September%202024.pdf",
                "coverage": "September 2024",
                "update_frequency": "Monthly (discontinued after Sep 2024)",
            },
            {
                "name": "CEAC Consular Scheduling Data",
                "description": "Scraped consular appointment data showing real-time consular pipeline activity. Provides consulate-level EB issuance counts and backlog estimates, plus NVC wait times. Validates DOS IV issuance projections.",
                "url": "https://github.com/underyx/visawhen",
                "coverage": "Mar 2017 – Aug 2024 (backlogs); Nov 2020 – present (NVC wait times)",
                "update_frequency": "Automated (daily via GitHub Actions)",
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
        last_verified="2026-06-01",
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


class DependentMultiplierResponse(BaseModel):
    """DHS Yearbook Table 7 dependent multiplier data."""
    available_years: List[int]
    latest_year: int
    latest_multipliers: dict[str, float]
    average_multipliers_5yr: dict[str, float]
    historical: dict[str, list[dict]]  # {category: [{fiscal_year, multiplier, ...}]}
    notes: dict


@app.get("/api/dependent-multipliers", response_model=DependentMultiplierResponse)
async def get_dependent_multipliers():
    """Returns dependent multiplier data from DHS Yearbook Table 7.

    Shows how many total persons (principals + spouses + children) are admitted
    per EB category for each I-140 principal. Used to convert I-140 pipeline
    counts (principal-only) into total visa demand.

    Data source: DHS Yearbook of Immigration Statistics, Table 7 —
    Persons Obtaining LPR Status by Type and Detailed Class of Admission.
    FY2015–FY2023.
    """
    try:
        parser = DhsYearbookParser()
        summary = parser.get_summary()

        historical: dict[str, list[dict]] = {}
        for cat in ["EB1", "EB2", "EB3", "EB4", "EB5"]:
            historical[cat] = parser.get_category_detail(cat)

        return DependentMultiplierResponse(
            available_years=summary["available_years"],
            latest_year=summary["latest_year"],
            latest_multipliers=summary["latest_multipliers"],
            average_multipliers_5yr=summary["average_multipliers_5yr"],
            historical=historical,
            notes=summary["notes"],
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class I140ReceiptFYData(BaseModel):
    fiscal_year: int
    receipts: int
    approved: int
    denied: int
    pending: int
    approval_rate: float
    eb1_receipts: int
    eb2_receipts: int
    eb3_receipts: int


class I140ReceiptGrowth(BaseModel):
    fiscal_year: int
    receipts: int
    yoy_growth_pct: float | None
    eb1_growth_pct: float | None
    eb2_growth_pct: float | None
    eb3_growth_pct: float | None


class I140ReceiptCountry(BaseModel):
    country: str
    receipts: int
    eb1: int
    eb2: int
    eb3: int
    share_pct: float


class I140ReceiptsResponse(BaseModel):
    """I-140 Receipts (New Filings) — queue growth rate data."""
    all_countries: list[I140ReceiptFYData]
    india: list[I140ReceiptFYData]
    growth_rates: list[I140ReceiptGrowth]
    india_growth_rates: list[I140ReceiptGrowth]
    country_comparison: list[I140ReceiptCountry]
    summary: dict


@app.get("/api/i140-receipts", response_model=I140ReceiptsResponse)
async def get_i140_receipts():
    """Returns I-140 receipt (new filing) data — separate from approved/pipeline.

    Shows how fast new EB petitions are entering the system. This models
    the queue growth rate: each receipt is a new I-140 petition filed with USCIS.

    Key distinction from the pipeline endpoint (/api/inventory-context):
    - Pipeline = approved I-140s waiting for visa numbers (existing queue)
    - Receipts = NEW I-140s being filed (inflow rate / queue growth)

    Data source: USCIS I-140 Receipts by Classification and Country (quarterly).
    """
    try:
        parser = I140ReceiptsParser.latest()
        return I140ReceiptsResponse(
            all_countries=[I140ReceiptFYData(**d) for d in parser.get_receipts_by_fy("All")],
            india=[I140ReceiptFYData(**d) for d in parser.get_receipts_by_fy("India")],
            growth_rates=[I140ReceiptGrowth(**d) for d in parser.get_growth_rates("All")],
            india_growth_rates=[I140ReceiptGrowth(**d) for d in parser.get_growth_rates("India")],
            country_comparison=[I140ReceiptCountry(**d) for d in parser.get_country_comparison()],
            summary=parser.get_summary(),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
