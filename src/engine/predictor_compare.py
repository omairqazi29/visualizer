"""Shared VBPredictor vs DemandModeler comparison (API + CLI)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from .demand import DemandModeler
from .supply import SupplyCalculator
from .vb_predictor import VBPredictor
from ..parsers.inventory_parser import InventoryParser
from ..parsers.pipeline_parser import PipelineParser

VALID_CATEGORIES = frozenset({"EB-1", "EB-2", "EB-3"})


def build_predictor_compare(
    priority_date: str,
    category: str = "EB-1",
    apply_real_restrictions: bool = False,
) -> dict[str, Any]:
    """Side-by-side demand burn-down vs VB FAD trend for one PD.

    Raises ValueError if priority_date is not YYYY-MM-DD or category invalid.
    """
    if category not in VALID_CATEGORIES:
        raise ValueError(f"category must be one of {sorted(VALID_CATEGORIES)}")
    try:
        pd_dt = datetime.strptime(priority_date, "%Y-%m-%d")
    except ValueError as exc:
        raise ValueError("priority_date must be in YYYY-MM-DD format") from exc

    notes: list[str] = []
    assumptions: dict[str, Any] = {
        "demand_engine": "DemandModeler — backlog ahead of PD / FY supply schedule",
        "vb_engine": "VBPredictor — historical FAD advancement + seasonal pattern",
        "category": category,
        "supply_scaling": (
            "India EB-1 supply only when category=EB-1; other categories use factor 1.0"
        ),
    }

    demand_months = None
    demand_clearance = None
    demand_backlog = None
    demand_supply = None
    demand_score = None

    if category != "EB-1":
        notes.append(
            f"DemandModeler path is implemented for India EB-1 only; "
            f"category={category} returns VB-only comparison."
        )
    else:
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
            backlog_ahead = inv_stats_total["total"] + int(pipe_total * pipeline_fraction)
        else:
            backlog_ahead = inv_ahead.get("mountain", inv_ahead["total"])

        calc = SupplyCalculator()
        monthly_dist = calc.dos_parser.get_monthly_distribution(
            country="India", categories=["E11", "E12", "E13"]
        )
        fy_supply = calc.get_supply_by_fy(
            apply_freeze=False, apply_real_restrictions=apply_real_restrictions
        )
        modeler = DemandModeler(
            total_queue, monthly_distribution=monthly_dist, fy_supply=fy_supply
        )
        demand_supply = int(modeler.default_supply)
        demand_score = float(
            modeler.calculate_confidence_score(
                pd_dt, backlog_ahead=backlog_ahead, target_fy=2027
            )
        )
        projection = modeler.project_clearance(backlog=backlog_ahead)
        demand_months = int(projection["months_to_clear"])
        demand_clearance = projection["clearance_date"].strftime("%Y-%m-%d")
        demand_backlog = int(backlog_ahead)
        assumptions["demand_total_queue"] = int(total_queue)
        assumptions["demand_fy_supply_keys"] = sorted(fy_supply.keys())

    predictor = VBPredictor(category=category)
    # Only scale VB advancement with India EB-1 supply when forecasting EB-1
    supply = None
    if apply_real_restrictions and category == "EB-1":
        supply = SupplyCalculator().get_supply_breakdown(
            apply_real_restrictions=True
        ).india_eb1_supply
    elif apply_real_restrictions and category != "EB-1":
        notes.append(
            f"Restriction supply scaling is India EB-1 only; "
            f"VB forecast for {category} uses supply_factor=1.0 (no category-specific model)."
        )

    vb_result = predictor.forecast(months_ahead=60, annual_supply=supply)
    vb_reach = predictor.months_until_fad_reaches(priority_date, forecast_result=vb_result)
    latest = vb_result.get("latest_actual") or {}
    stats = vb_result.get("stats") or {}

    vb_months = vb_reach.get("months_to_current")
    if latest.get("fad_unavailable") and demand_months is not None:
        notes.append(
            "Latest VB FAD is Unavailable — trend forecast anchors on prior dated FAD; "
            "demand path still burns queue (assumes numbers resume at FY supply rate)."
        )
    elif latest.get("fad_unavailable"):
        notes.append(
            "Latest VB FAD is Unavailable — VB-only compare; forecast assumes numbers "
            "resume at historical advancement rates (optimistic vs FY-end U narrative)."
        )
    if vb_months is None and demand_months is not None:
        notes.append(
            "VB forecast did not reach PD within 60 months (slow/negative recent advancement "
            "or deep retrogression); demand path may still clear via supply schedule."
        )

    months_delta = None
    if demand_months is not None and vb_months is not None:
        months_delta = int(demand_months) - int(vb_months)
        if abs(months_delta) > 12:
            notes.append(
                f"Large divergence ({months_delta:+d} mo): demand uses inventory queue + "
                "FY supply; VB uses historical FAD days/month (includes retrogressions)."
            )

    return {
        "priority_date": priority_date,
        "category": category,
        "apply_real_restrictions": apply_real_restrictions,
        "demand_months_to_clear": demand_months,
        "demand_projected_clearance_date": demand_clearance,
        "demand_backlog_ahead": demand_backlog,
        "demand_annual_supply": demand_supply,
        "demand_confidence_score": demand_score,
        "vb_months_to_current": vb_months,
        "vb_estimated_bulletin_month": vb_reach.get("estimated_bulletin_month"),
        "vb_confidence": vb_reach.get("confidence"),
        "vb_latest_fad": latest.get("fad"),
        "vb_latest_fad_status": latest.get("fad_status"),
        "vb_fad_unavailable": bool(latest.get("fad_unavailable", False)),
        "vb_category_unavailable": bool(vb_reach.get("category_unavailable", False)),
        "vb_assumes_numbers_resume": bool(vb_reach.get("assumes_numbers_resume", False)),
        "vb_supply_factor": vb_result.get("supply_factor"),
        "vb_recent_avg_days_per_month": stats.get("recent_avg"),
        "months_delta": months_delta,
        "divergence_notes": notes,
        "assumptions": assumptions,
        "methodology_vb": vb_result.get("methodology"),
    }
