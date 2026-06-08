"""Visa Bulletin Predictor — forecasts future FAD/DOF dates.

Uses historical VB data to decompose FAD movement into:
1. Base advancement rate (days per bulletin month)
2. Seasonal modulation (fiscal month patterns — DOS issues more Oct-Dec, less Jul-Sep)
3. Supply-adjusted scaling (higher supply → faster advancement)

Produces month-by-month forecast with confidence bands.
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
            calendar_month, fiscal_month

        Only includes transitions between two consecutive non-Current FADs.
        Negative advancement_days = retrogression.
        """
        history = self.vb.get_history()

        if len(history) < 2:
            return []

        rates: list[dict] = []
        for i in range(1, len(history)):
            prev = history[i - 1]
            curr = history[i]

            # Only include pairs where both FADs are non-Current
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
            })

        return rates

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
            recent_avg: float — avg days/month over last N months
            recent_median: float
            recent_stdev: float
            overall_avg: float
            seasonal_pattern: dict[int, float]
            n_datapoints: int
            retrogression_count: int — months with negative advancement
        """
        rates = self.get_advancement_rates()

        if not rates:
            return {
                "recent_avg": 0.0,
                "recent_median": 0.0,
                "recent_stdev": 15.0,
                "overall_avg": 0.0,
                "seasonal_pattern": {fm: 0.0 for fm in range(1, 13)},
                "n_datapoints": 0,
                "retrogression_count": 0,
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
        }

    def forecast(
        self,
        months_ahead: int = 24,
        annual_supply: int | None = None,
        baseline_supply: int = DEFAULT_INDIA_EB1_SUPPLY,
    ) -> dict:
        """Forecast FAD/DOF for the next N months.

        Methodology:
        1. Compute recent advancement rate (last 12 months weighted higher)
        2. Apply seasonal modulation:
           blended_rate = 0.7 * recent_avg + 0.3 * seasonal_avg_for_fiscal_month
        3. Supply scaling: if annual_supply provided,
           scale by (annual_supply / baseline_supply), capped at 3.0x
        4. Confidence bands: widen at sqrt(months_ahead) * recent_stdev

        Returns:
        {
            "forecast": [
                {
                    "bulletin_month": "2026-07",
                    "predicted_fad": "2023-05-15",
                    "predicted_dof": "2024-01-01",
                    "fad_confidence_low": "2023-03-01",
                    "fad_confidence_high": "2023-08-01",
                }, ...
            ],
            "latest_actual": {
                "bulletin_month": "2026-06",
                "fad": "2022-12-15",
                "dof": "2023-12-01",
            },
            "stats": { ... },
            "supply_factor": 1.0,
            "dof_gap_months": 9.5,
            "methodology": "descriptive string",
        }
        """
        history = self.vb.get_history()
        stats = self.get_advancement_stats()
        seasonal = stats["seasonal_pattern"]

        # --- Locate latest actuals ---
        # Latest bulletin month (last row in history)
        if not history:
            return {
                "forecast": [],
                "latest_actual": {"bulletin_month": None, "fad": None, "dof": None},
                "stats": stats,
                "supply_factor": 1.0,
                "dof_gap_months": 0.0,
                "methodology": "No historical data available; cannot forecast.",
            }

        latest_row = history[-1]
        latest_bm = latest_row["bulletin_month"]

        # Find latest non-Current FAD (starting point for forecast)
        latest_fad: Optional[date] = None
        for r in reversed(history):
            if r["fad"] is not None:
                latest_fad = r["fad"]
                break

        # Find latest non-Current DOF
        latest_dof: Optional[date] = None
        for r in reversed(history):
            if r["dof"] is not None:
                latest_dof = r["dof"]
                break

        # Edge case: all history is Current — no FAD to anchor forecast
        if latest_fad is None:
            return {
                "forecast": [],
                "latest_actual": {
                    "bulletin_month": latest_bm,
                    "fad": None,
                    "dof": latest_dof.isoformat() if latest_dof else None,
                },
                "stats": stats,
                "supply_factor": 1.0,
                "dof_gap_months": 0.0,
                "methodology": (
                    "All historical FADs are Current (no retrogression); "
                    "cannot forecast date advancement."
                ),
            }

        # --- DOF-FAD gap ---
        dof_info = self.vb.get_dof_lead_months()
        dof_gap_months: float = dof_info.get("median_gap", 0.0)

        # --- Supply scaling ---
        supply_factor = 1.0
        if annual_supply is not None and baseline_supply > 0:
            supply_factor = min(3.0, annual_supply / baseline_supply)

        # --- Advancement parameters ---
        recent_avg = stats["recent_avg"]
        # Minimum stdev of 15 days for confidence bands
        recent_std = max(15.0, stats["recent_stdev"])

        # Earliest known FAD as retrogression floor
        all_fads = [r["fad"] for r in history if r["fad"] is not None]
        earliest_fad = min(all_fads)

        # --- Parse starting bulletin month ---
        parts = latest_bm.split("-")
        bm_year, bm_month = int(parts[0]), int(parts[1])

        # --- Build month-by-month forecast ---
        forecast_list: list[dict] = []
        current_fad = latest_fad

        for i in range(months_ahead):
            bm_year, bm_month = _next_month(bm_year, bm_month)
            fm = _fiscal_month(bm_month)

            # Blended advancement: 70% recent average + 30% seasonal for this FM
            seasonal_rate = seasonal.get(fm, recent_avg)
            base_advancement = 0.7 * recent_avg + 0.3 * seasonal_rate

            # Apply supply scaling
            base_advancement *= supply_factor

            # Advance FAD
            new_fad = current_fad + timedelta(days=round(base_advancement))

            # Clamp: FAD should not go before the earliest known retrogression
            if new_fad < earliest_fad:
                new_fad = earliest_fad

            # Confidence bands widen with sqrt(month_index)
            band_width = round(recent_std * sqrt(i + 1))
            conf_low = new_fad - timedelta(days=band_width)
            conf_high = new_fad + timedelta(days=band_width)

            # Clamp low confidence bound
            if conf_low < earliest_fad:
                conf_low = earliest_fad

            # DOF estimate: FAD + median gap
            predicted_dof: Optional[date] = None
            if dof_gap_months > 0:
                dof_delta = timedelta(days=round(dof_gap_months * 30.44))
                predicted_dof = new_fad + dof_delta

            bm_str = f"{bm_year:04d}-{bm_month:02d}"
            forecast_list.append({
                "bulletin_month": bm_str,
                "predicted_fad": new_fad.isoformat(),
                "predicted_dof": predicted_dof.isoformat() if predicted_dof else None,
                "fad_confidence_low": conf_low.isoformat(),
                "fad_confidence_high": conf_high.isoformat(),
            })

            current_fad = new_fad

        # --- Assemble result ---
        latest_actual = {
            "bulletin_month": latest_bm,
            "fad": latest_fad.isoformat(),
            "dof": latest_dof.isoformat() if latest_dof else None,
        }

        methodology = (
            f"Blended forecast using {stats['n_datapoints']} historical data points: "
            f"70% recent-12 avg ({recent_avg:.0f} days/mo) + "
            f"30% seasonal pattern by fiscal month. "
            f"Supply factor {supply_factor:.2f}x"
            f"{f' (annual_supply={annual_supply:,})' if annual_supply is not None else ''}. "
            f"Confidence bands widen at sqrt(month) × {recent_std:.0f} days. "
            f"DOF estimated at FAD + {dof_gap_months:.1f} month gap (median of recent data)."
        )

        return {
            "forecast": forecast_list,
            "latest_actual": latest_actual,
            "stats": stats,
            "supply_factor": supply_factor,
            "dof_gap_months": dof_gap_months,
            "methodology": methodology,
        }
