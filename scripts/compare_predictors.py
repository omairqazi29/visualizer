#!/usr/bin/env python3
"""Compare VBPredictor vs DemandModeler for a priority date.

Runs locally against the in-process engines (no server required), or optionally
hits a running API via --base-url.

Usage:
  python scripts/compare_predictors.py --priority-date 2022-10-01
  python scripts/compare_predictors.py --priority-date 2023-04-01 --restrictions
  python scripts/compare_predictors.py --priority-date 2022-10-01 --base-url http://localhost:8000
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Allow running from repo root without installing the package
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def compare_local(priority_date: str, category: str, restrictions: bool) -> dict:
    """In-process comparison (same logic as /api/predictor-compare)."""
    from datetime import datetime

    from src.engine.demand import DemandModeler
    from src.engine.supply import SupplyCalculator
    from src.engine.vb_predictor import VBPredictor
    from src.parsers.inventory_parser import InventoryParser
    from src.parsers.pipeline_parser import PipelineParser

    pd_dt = datetime.strptime(priority_date, "%Y-%m-%d")
    notes: list[str] = []
    out: dict = {
        "priority_date": priority_date,
        "category": category,
        "apply_real_restrictions": restrictions,
    }

    # Demand (EB-1 India only)
    if category == "EB-1":
        inv = InventoryParser.latest()
        inv_total = inv.get_india_eb1_queue()
        pipe = PipelineParser.latest()
        pipe.load_data()
        pipe_total = pipe.get_india_eb1_backlog()
        total_queue = inv_total["total"] + pipe_total
        inv_ahead = inv.get_india_eb1_queue(cutoff_month=pd_dt.month, cutoff_year=pd_dt.year)
        if pd_dt.year > 2023:
            months_into = (pd_dt.year - 2024) * 12 + pd_dt.month
            frac = min(1.0, months_into / 24.0)
            backlog = inv_total["total"] + int(pipe_total * frac)
        else:
            backlog = inv_ahead.get("mountain", inv_ahead["total"])

        calc = SupplyCalculator()
        monthly = calc.dos_parser.get_monthly_distribution(
            country="India", categories=["E11", "E12", "E13"]
        )
        fy_supply = calc.get_supply_by_fy(
            apply_freeze=False, apply_real_restrictions=restrictions
        )
        modeler = DemandModeler(total_queue, monthly_distribution=monthly, fy_supply=fy_supply)
        proj = modeler.project_clearance(backlog=backlog)
        out["demand_months_to_clear"] = int(proj["months_to_clear"])
        out["demand_projected_clearance_date"] = proj["clearance_date"].strftime("%Y-%m-%d")
        out["demand_backlog_ahead"] = int(backlog)
        out["demand_annual_supply"] = int(modeler.default_supply)
        out["demand_confidence_score"] = float(
            modeler.calculate_confidence_score(pd_dt, backlog_ahead=backlog, target_fy=2027)
        )
    else:
        notes.append("Demand path is EB-1 only in this script.")
        out["demand_months_to_clear"] = None

    predictor = VBPredictor(category=category)
    supply = None
    if restrictions:
        supply = SupplyCalculator().get_supply_breakdown(
            apply_real_restrictions=True
        ).india_eb1_supply
    vb_result = predictor.forecast(months_ahead=60, annual_supply=supply)
    reach = predictor.months_until_fad_reaches(priority_date, forecast_result=vb_result)
    latest = vb_result.get("latest_actual") or {}
    stats = vb_result.get("stats") or {}

    out["vb_months_to_current"] = reach.get("months_to_current")
    out["vb_estimated_bulletin_month"] = reach.get("estimated_bulletin_month")
    out["vb_confidence"] = reach.get("confidence")
    out["vb_latest_fad"] = latest.get("fad")
    out["vb_latest_fad_status"] = latest.get("fad_status")
    out["vb_fad_unavailable"] = bool(latest.get("fad_unavailable"))
    out["vb_supply_factor"] = vb_result.get("supply_factor")
    out["vb_recent_avg_days_per_month"] = stats.get("recent_avg")

    dm = out.get("demand_months_to_clear")
    vm = out.get("vb_months_to_current")
    if dm is not None and vm is not None:
        out["months_delta"] = int(dm) - int(vm)
        if abs(out["months_delta"]) > 12:
            notes.append(
                f"Large divergence ({out['months_delta']:+d} mo): demand uses inventory+supply; "
                "VB uses historical FAD advancement (includes retrogression)."
            )
    else:
        out["months_delta"] = None

    if latest.get("fad_unavailable"):
        notes.append("Latest FAD is Unavailable — VB anchors on prior dated FAD.")

    out["divergence_notes"] = notes
    out["methodology_vb"] = vb_result.get("methodology")
    return out


def compare_api(base_url: str, priority_date: str, category: str, restrictions: bool) -> dict:
    import urllib.parse
    import urllib.request

    params = urllib.parse.urlencode({
        "priority_date": priority_date,
        "category": category,
        "apply_real_restrictions": str(restrictions).lower(),
    })
    url = f"{base_url.rstrip('/')}/api/predictor-compare?{params}"
    with urllib.request.urlopen(url, timeout=60) as resp:
        return json.loads(resp.read().decode())


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare VB vs demand predictors")
    parser.add_argument("--priority-date", required=True, help="YYYY-MM-DD")
    parser.add_argument("--category", default="EB-1")
    parser.add_argument("--restrictions", action="store_true")
    parser.add_argument(
        "--base-url",
        default=None,
        help="If set, call /api/predictor-compare on this host (e.g. http://localhost:8000)",
    )
    args = parser.parse_args()

    if args.base_url:
        result = compare_api(args.base_url, args.priority_date, args.category, args.restrictions)
    else:
        result = compare_local(args.priority_date, args.category, args.restrictions)

    print(json.dumps(result, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
