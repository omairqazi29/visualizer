"""Visa Bulletin Predictor — forecasts future FAD/DOF dates.

Uses historical VB data to decompose FAD movement into:
1. Base advancement rate (days per bulletin month)
2. Seasonal modulation (fiscal month patterns — DOS issues more Oct-Dec, less Jul-Sep)
3. Supply-adjusted scaling (higher supply → faster advancement)

Produces month-by-month forecast with confidence bands.

Unavailable ("U") months are excluded from advancement-rate statistics
(no dated FAD to measure). Current ("C") months are likewise excluded.
Forecast anchors on the latest *dated* FAD; if the latest bulletin is U,
latest_actual reflects status=U with fad=None and methodology notes the gap.
"""

from collections import defaultdict
from datetime import date, timedelta
from math import sqrt
from statistics import mean, median, stdev
from typing import Optional

from ..parsers.visa_bulletin_parser import VisaBulletinParser
from ..constants import DEFAULT_INDIA_EB1_SUPPLY


def _fiscal_month(cal_month: int) -> int:
    """Calendar month (1=Jan) to fiscal month (1=Oct, 12=Sep)."""
    return (cal_month - 10) % 12 + 1


def _next_month(year: int, month: int) -> tuple[int, int]:
    """Advance to the next calendar month."""
    if month == 12:
        return year + 1, 1
    return year, month + 1


def _resolve_baseline_supply() -> int:
    """Prefer live supply-model baseline (FY2024 India EB-1) over constant."""
    try:
        from .supply import SupplyCalculator
        calc = SupplyCalculator()
        breakdown = calc.get_supply_breakdown(apply_freeze=False, apply_real_restrictions=False)
        # Baseline India EB-1 from supply model (data-driven, not hardcoded result)
        return int(breakdown.india_eb1_baseline or DEFAULT_INDIA_EB1_SUPPLY)
    except Exception:
        return DEFAULT_INDIA_EB1_SUPPLY


class VBPredictor:
    """Forecasts future Visa Bulletin dates using historical patterns."""

    def __init__(self, category: str = "EB-1", country: str = "India"):
        self.category = category
        self.country = country
        self.vb = VisaBulletinParser(category=category, country=country)

    def get_advancement_rates(self) -> list[dict]:
        """Month-over-month FAD advancement in days.

        Returns list of dicts:
            bulletin_month, fad, prev_fad, advancement_days,
            calendar_month, fiscal_month, skipped_unavailable

        Only includes transitions between two consecutive *dated* FADs.
        Transitions involving Current ("C") or Unavailable ("U") are skipped
        (no measurable advancement). Negative advancement_days = retrogression.
        """
        history = self.vb.get_history()

        if len(history) < 2:
            return []

        rates: list[dict] = []
        for i in range(1, len(history)):
            prev = history[i - 1]
            curr = history[i]

            # Skip pairs involving Current or Unavailable (no dated FAD)
            if prev["fad"] is None or curr["fad"] is None:
                continue

            delta_days = (curr["fad"] - prev["fad"]).days
            parts = curr["bulletin_month"].split("-")
            cal_month = int(parts[1])

            rates.append({
                "bulletin_month": curr["bulletin_month"],
                "fad": curr["fad"],
                "prev_fad": prev["fad"],
                "advancement_days": delta_days,
                "calendar_month": cal_month,
                "fiscal_month": _fiscal_month(cal_month),
                "from_unavailable": bool(prev.get("fad_unavailable")),
                "to_unavailable": bool(curr.get("fad_unavailable")),
            })

        return rates

    def count_unavailable_months(self) -> int:
        """Count bulletin months where FAD was Unavailable."""
        return sum(1 for r in self.vb.get_history() if r.get("fad_unavailable"))

    def get_seasonal_pattern(self) -> dict[int, float]:
        """Average FAD advancement (days) by fiscal month.

        Returns {fiscal_month: avg_days}.
        FM 1=Oct, 2=Nov, ..., 12=Sep.
        """
        rates = self.get_advancement_rates()

        if not rates:
            return {fm: 0.0 for fm in range(1, 13)}

        # Group advancement by fiscal month
        by_fm: dict[int, list[float]] = defaultdict(list)
        for r in rates:
            by_fm[r["fiscal_month"]].append(r["advancement_days"])

        # Overall average as fallback for fiscal months with no data
        all_adv = [float(r["advancement_days"]) for r in rates]
        overall_avg = mean(all_adv)

        pattern: dict[int, float] = {}
        for fm in range(1, 13):
            if fm in by_fm and by_fm[fm]:
                pattern[fm] = round(mean([float(d) for d in by_fm[fm]]), 1)
            else:
                pattern[fm] = round(overall_avg, 1)

        return pattern

    def get_advancement_stats(self, recent_n: int = 12) -> dict:
        """Summary stats on FAD advancement rates.

        Returns:
            recent_avg: float — avg days/month over last N dated transitions
            recent_median: float
            recent_stdev: float
            overall_avg: float
            seasonal_pattern: dict[int, float]
            n_datapoints: int
            retrogression_count: int — months with negative advancement
            unavailable_months: int — bulletin months with FAD=U
        """
        rates = self.get_advancement_rates()
        unavailable_months = self.count_unavailable_months()

        if not rates:
            return {
                "recent_avg": 0.0,
                "recent_median": 0.0,
                "recent_stdev": 15.0,
                "overall_avg": 0.0,
                "seasonal_pattern": {fm: 0.0 for fm in range(1, 13)},
                "n_datapoints": 0,
                "retrogression_count": 0,
                "unavailable_months": unavailable_months,
            }

        all_adv = [r["advancement_days"] for r in rates]
        recent = all_adv[-recent_n:]

        recent_avg = mean(recent)
        recent_med = median(recent)
        # Need at least 2 data points for stdev; use minimum of 15 days
        recent_std = stdev(recent) if len(recent) >= 2 else 15.0

        return {
            "recent_avg": round(recent_avg, 1),
            "recent_median": round(recent_med, 1),
            "recent_stdev": round(recent_std, 1),
            "overall_avg": round(mean(all_adv), 1),
            "seasonal_pattern": self.get_seasonal_pattern(),
            "n_datapoints": len(rates),
            "retrogression_count": sum(1 for a in all_adv if a < 0),
            "unavailable_months": unavailable_months,
        }

    def months_until_fad_reaches(self, priority_date: str | date, forecast_result: dict | None = None) -> dict:
        """Estimate months until forecasted FAD passes priority_date.

        Returns {months_to_current, estimated_bulletin_month, confidence}.
        If already current or no forecast, months_to_current=0 / None.
        """
        if isinstance(priority_date, str):
            pd_date = date.fromisoformat(priority_date)
        else:
            pd_date = priority_date

        result = forecast_result or self.forecast(months_ahead=60)
        status = self.vb.get_current_status(pd_date.isoformat())

        if status.get("fad_unavailable"):
            # Category closed — wait for numbers to resume; use forecast if any
            pass
        elif status.get("fad_is_current"):
            return {
                "months_to_current": 0,
                "estimated_bulletin_month": status.get("bulletin_month"),
                "confidence": "high",
                "already_current": True,
            }

        for i, pt in enumerate(result.get("forecast") or [], start=1):
            pred = pt.get("predicted_fad")
            if not pred:
                continue
            if pd_date < date.fromisoformat(pred):
                # Wider confidence bands → lower confidence further out
                conf = "high" if i <= 6 else ("medium" if i <= 18 else "low")
                return {
                    "months_to_current": i,
                    "estimated_bulletin_month": pt["bulletin_month"],
                    "confidence": conf,
                    "already_current": False,
                }

        return {
            "months_to_current": None,
            "estimated_bulletin_month": None,
            "confidence": "low",
            "already_current": False,
        }

    def forecast(
        self,
        months_ahead: int = 24,
        annual_supply: int | None = None,
        baseline_supply: int | None = None,
    ) -> dict:
        """Forecast FAD/DOF for the next N months.

        Methodology:
        1. Compute recent advancement rate (last 12 dated transitions)
        2. Apply seasonal modulation:
           blended_rate = 0.7 * recent_avg + 0.3 * seasonal_avg_for_fiscal_month
        3. Supply scaling: if annual_supply provided,
           scale by (annual_supply / baseline_supply), capped at 3.0x
           baseline_supply defaults to supply-model India EB-1 baseline
        4. Confidence bands: widen at sqrt(months_ahead) * recent_stdev

        Unavailable / Current latest rows are reflected in latest_actual status
        fields; forecast still anchors on latest dated FAD.
        """
        history = self.vb.get_history()
        stats = self.get_advancement_stats()
        seasonal = stats["seasonal_pattern"]

        if baseline_supply is None:
            baseline_supply = _resolve_baseline_supply()

        # --- Locate latest actuals ---
        if not history:
            return {
                "forecast": [],
                "latest_actual": {
                    "bulletin_month": None,
                    "fad": None,
                    "dof": None,
                    "fad_status": "C",
                    "dof_status": "C",
                    "fad_unavailable": False,
                    "dof_unavailable": False,
                },
                "stats": stats,
                "supply_factor": 1.0,
                "dof_gap_months": 0.0,
                "methodology": "No historical data available; cannot forecast.",
            }

        latest_row = history[-1]
        latest_bm = latest_row["bulletin_month"]
        latest_fad_status = latest_row.get("fad_status", "date" if latest_row.get("fad") else "C")
        latest_dof_status = latest_row.get("dof_status", "date" if latest_row.get("dof") else "C")

        # Find latest dated FAD (starting point for forecast) — walk past U/C
        latest_fad: Optional[date] = None
        for r in reversed(history):
            if r["fad"] is not None:
                latest_fad = r["fad"]
                break

        latest_dof: Optional[date] = None
        for r in reversed(history):
            if r["dof"] is not None:
                latest_dof = r["dof"]
                break

        latest_actual = {
            "bulletin_month": latest_bm,
            # Prefer the *latest bulletin's* FAD (may be None if U/C)
            "fad": latest_row["fad"].isoformat() if latest_row.get("fad") else None,
            "dof": latest_row["dof"].isoformat() if latest_row.get("dof") else None,
            "fad_status": latest_fad_status,
            "dof_status": latest_dof_status,
            "fad_unavailable": bool(latest_row.get("fad_unavailable")),
            "dof_unavailable": bool(latest_row.get("dof_unavailable")),
            # Anchor used for forecast (may differ from latest bulletin if U)
            "forecast_anchor_fad": latest_fad.isoformat() if latest_fad else None,
        }

        # Edge case: all history is Current/Unavailable — no FAD to anchor
        if latest_fad is None:
            reason = (
                "Latest FAD is Unavailable and no prior dated FAD exists; cannot forecast."
                if latest_row.get("fad_unavailable")
                else "All historical FADs are Current (no retrogression); cannot forecast date advancement."
            )
            return {
                "forecast": [],
                "latest_actual": latest_actual,
                "stats": stats,
                "supply_factor": 1.0,
                "dof_gap_months": 0.0,
                "methodology": reason,
            }

        # --- DOF-FAD gap (dated months only) ---
        dof_info = self.vb.get_dof_lead_months()
        dof_gap_months: float = dof_info.get("median_gap", 0.0)

        # --- Supply scaling ---
        supply_factor = 1.0
        if annual_supply is not None and baseline_supply > 0:
            supply_factor = min(3.0, annual_supply / baseline_supply)

        # --- Advancement parameters ---
        recent_avg = stats["recent_avg"]
        recent_std = max(15.0, stats["recent_stdev"])

        all_fads = [r["fad"] for r in history if r["fad"] is not None]
        earliest_fad = min(all_fads)

        parts = latest_bm.split("-")
        bm_year, bm_month = int(parts[0]), int(parts[1])

        forecast_list: list[dict] = []
        current_fad = latest_fad

        for i in range(months_ahead):
            bm_year, bm_month = _next_month(bm_year, bm_month)
            fm = _fiscal_month(bm_month)

            seasonal_rate = seasonal.get(fm, recent_avg)
            base_advancement = 0.7 * recent_avg + 0.3 * seasonal_rate
            base_advancement *= supply_factor

            new_fad = current_fad + timedelta(days=round(base_advancement))

            if new_fad < earliest_fad:
                new_fad = earliest_fad

            band_width = round(recent_std * sqrt(i + 1))
            conf_low = new_fad - timedelta(days=band_width)
            conf_high = new_fad + timedelta(days=band_width)

            if conf_low < earliest_fad:
                conf_low = earliest_fad

            predicted_dof: Optional[date] = None
            if dof_gap_months > 0:
                dof_delta = timedelta(days=round(dof_gap_months * 30.44))
                predicted_dof = new_fad + dof_delta
            elif latest_dof is not None:
                # Fallback: preserve latest DOF offset from anchor FAD
                offset = (latest_dof - latest_fad).days
                if offset > 0:
                    predicted_dof = new_fad + timedelta(days=offset)

            bm_str = f"{bm_year:04d}-{bm_month:02d}"
            forecast_list.append({
                "bulletin_month": bm_str,
                "predicted_fad": new_fad.isoformat(),
                "predicted_dof": predicted_dof.isoformat() if predicted_dof else None,
                "fad_confidence_low": conf_low.isoformat(),
                "fad_confidence_high": conf_high.isoformat(),
            })

            current_fad = new_fad

        unavail_note = ""
        if latest_row.get("fad_unavailable"):
            unavail_note = (
                f" Latest bulletin ({latest_bm}) FAD is Unavailable; "
                f"forecast anchored on prior dated FAD {latest_fad.isoformat()}."
            )
        elif stats.get("unavailable_months", 0) > 0:
            unavail_note = (
                f" {stats['unavailable_months']} historical Unavailable month(s) "
                "excluded from advancement stats."
            )

        methodology = (
            f"Blended forecast using {stats['n_datapoints']} dated transitions: "
            f"70% recent-12 avg ({recent_avg:.0f} days/mo) + "
            f"30% seasonal pattern by fiscal month. "
            f"Supply factor {supply_factor:.2f}x"
            f"{f' (annual_supply={annual_supply:,}, baseline={baseline_supply:,})' if annual_supply is not None else ''}. "
            f"Confidence bands widen at sqrt(month) × {recent_std:.0f} days. "
            f"DOF estimated at FAD + {dof_gap_months:.1f} month gap (median of recent dated data)."
            f"{unavail_note}"
        )

        return {
            "forecast": forecast_list,
            "latest_actual": latest_actual,
            "stats": stats,
            "supply_factor": supply_factor,
            "dof_gap_months": dof_gap_months,
            "methodology": methodology,
        }
