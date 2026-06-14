"""Oppenheim FAD Solver — predicts FAD via demand-supply equilibrium.

Models how Charlie Oppenheim at DOS sets the Final Action Date (FAD):
find the priority-date cutoff where pending I-485 demand, scaled by a
materialization rate, approximately equals the monthly visa supply target.

This is the third prediction engine in The Spillover Engine, bridging:
- VBPredictor  — trend extrapolation (historical avg days/month advancement)
- DemandModeler — backlog burn-down (total queue ÷ annual supply)

The Oppenheim approach is more grounded in how DOS actually operates:
1. Compute annual visa supply from the INA 201/203 cascade
2. Divide by 12 for a monthly target
3. Find the FAD where eligible demand × materialization rate ≈ monthly target
4. Advance the FAD each month as cases are adjudicated

Key inputs (all data-driven, no hardcoded numbers):
- Supply: from SupplyCalculator (INA cascade, restriction scenarios)
- Demand: from InventoryParser.get_cumulative_demand() (USCIS I-485 inventory)
- Current FAD: from VisaBulletinParser (latest VB, for calibration)
- DOS monthly data: for YTD issuance estimation (consular-only, informational)
"""

import calendar
from dataclasses import dataclass
from datetime import date
from typing import Optional

from ..constants import DEFAULT_INDIA_EB1_SUPPLY
from ..parsers.dos_parser import DOSParser
from ..parsers.inventory_parser import InventoryParser
from ..parsers.pipeline_parser import PipelineParser
from ..parsers.visa_bulletin_parser import VisaBulletinParser
from .supply import SupplyCalculator, EB1_VISA_CATEGORIES


# ── Helpers ───────────────────────────────────────────


def _fiscal_month(cal_month: int) -> int:
    """Calendar month (1=Jan) → fiscal month (1=Oct, 12=Sep)."""
    return (cal_month - 10) % 12 + 1


def _fiscal_year(cal_month: int, cal_year: int) -> int:
    """Calendar (month, year) → fiscal year."""
    return cal_year + 1 if cal_month >= 10 else cal_year


def _next_cal_month(year: int, month: int) -> tuple[int, int]:
    """Advance to the next calendar month."""
    return (year + 1, 1) if month == 12 else (year, month + 1)


# Map user-facing category names → inventory parser keys
_CATEGORY_KEY_MAP: dict[str, str] = {
    "EB-1": "EB1", "EB-2": "EB2", "EB-3": "EB3",
    "EB-4": "EB4", "EB-5": "EB5",
    "EB1": "EB1", "EB2": "EB2", "EB3": "EB3",
    "EB4": "EB4", "EB5": "EB5",
}


# ── Data class ────────────────────────────────────────


@dataclass
class FADPrediction:
    """Single month's FAD prediction with confidence interval."""

    bulletin_month: str               # "2026-07"
    predicted_fad: date | None        # Predicted FAD (None = Current)
    is_current: bool                  # True when demand < supply/rate
    cumulative_demand: int            # I-485s with PD before predicted FAD
    target_monthly_supply: int        # Monthly visa target
    materialization_rate: float       # Rate used
    fiscal_year: int                  # FY this bulletin month belongs to

    # Confidence bounds (from varied materialization rates)
    fad_low: date | None = None       # Earlier FAD (high rate, pessimistic)
    fad_high: date | None = None      # Later FAD (low rate, optimistic)


# ── Solver ────────────────────────────────────────────


class OppenheimSolver:
    """Predicts FAD using Oppenheim's demand-supply matching algorithm.

    Algorithm:
    1. annual_supply = SupplyCalculator INA cascade for India EB-1
    2. target_monthly = annual_supply / 12
    3. target_demand = target_monthly / materialization_rate
    4. Binary search: find FAD where cumulative_demand(FAD) ≈ target_demand
    5. For trajectory: each month, target_demand increases by monthly_supply
       (accounting for cases issued in prior months)

    The materialization_rate is the fraction of eligible I-485 cases
    (PD < FAD) that consume a visa number in a given month.  Default
    0.65 — use calibrate() to compute from current VB data + supply.
    """

    DEFAULT_MATERIALIZATION_RATE: float = 0.65
    # Confidence band multipliers (applied to calibrated rate):
    # Lower rate → more demand needed → later FAD → optimistic for applicant
    # Higher rate → less demand needed → earlier FAD → pessimistic for applicant
    RATE_BAND_LOW: float = 0.70     # 70% of calibrated rate → fad_high (optimistic)
    RATE_BAND_HIGH: float = 1.40    # 140% of calibrated rate → fad_low (pessimistic)

    # Binary search year bounds (covers all PD years in inventory data)
    _MIN_YEAR: int = 2015
    _MAX_YEAR: int = 2028

    def __init__(
        self,
        category: str = "EB-1",
        country: str = "India",
        materialization_rate: float | None = None,
        dos_dir: str = "data/DOS",
        data_dir: str = "data",
        apply_real_restrictions: bool = True,
    ):
        self.category = category
        self.country = country
        self.materialization_rate = (
            materialization_rate if materialization_rate is not None
            else self.DEFAULT_MATERIALIZATION_RATE
        )
        self.dos_dir = dos_dir
        self.data_dir = data_dir
        self.apply_real_restrictions = apply_real_restrictions
        self._category_key = _CATEGORY_KEY_MAP.get(category, "EB1")

        # Lazy-loaded state
        self._supply_calc: Optional[SupplyCalculator] = None
        self._inv: Optional[InventoryParser] = None
        self._vb: Optional[VisaBulletinParser] = None
        self._annual_supply: Optional[int] = None
        self._fy_supply: Optional[dict[int, int]] = None
        self._total_demand_cache: Optional[int] = None
        self._shadow_ratio: Optional[float] = None

    # ── Lazy property accessors ───────────────────

    @property
    def supply_calculator(self) -> SupplyCalculator:
        """Centralized supply model (INA 201/203 cascade)."""
        if self._supply_calc is None:
            self._supply_calc = SupplyCalculator(dos_dir=self.dos_dir)
        return self._supply_calc

    @property
    def inventory(self) -> InventoryParser:
        """Latest USCIS I-485 inventory (auto-discovered)."""
        if self._inv is None:
            self._inv = InventoryParser.latest(data_dir=self.data_dir)
        return self._inv

    @property
    def visa_bulletin(self) -> VisaBulletinParser:
        """Historical Visa Bulletin data."""
        if self._vb is None:
            self._vb = VisaBulletinParser(
                category=self.category, country=self.country,
            )
        return self._vb

    # ── Shadow demand ──────────────────────────────

    def _get_shadow_demand_ratio(self) -> float:
        """Ratio of total effective demand to I-485 filed demand.

        As DOF advances, people with approved I-140s who haven't filed
        I-485 yet become eligible to file.  The I-140 pipeline contains
        these "shadow" cases.  The ratio = (I-485 + I-140) / I-485
        tells us how much the demand curve will inflate as dates advance.

        The inventory captures people who HAVE filed I-485 (both
        "Available" and "Awaiting Availability").  The I-140 pipeline
        captures approved I-140 primaries × dependent multiplier who
        have NOT yet filed I-485.

        Returns 1.0 if pipeline data is unavailable (no inflation).
        """
        if self._shadow_ratio is not None:
            return self._shadow_ratio

        try:
            pipe = PipelineParser.latest(data_dir=self.data_dir)
            pipeline = pipe.get_all_eb_pipeline()
            india = pipeline.get("India", {})
            i140_count = india.get(self._category_key, 0)
        except Exception:
            i140_count = 0

        # Use raw I-485 count (no shadow scaling) to avoid recursion
        i485_count = self.inventory.get_cumulative_demand(
            cutoff_year=2099, cutoff_month=1, category=self._category_key,
        )
        if i485_count <= 0:
            self._shadow_ratio = 1.0
        else:
            self._shadow_ratio = (i485_count + i140_count) / i485_count

        return self._shadow_ratio

    # ── Supply ────────────────────────────────────

    def _get_annual_supply(self, fy: int | None = None) -> int:
        """Data-driven India EB-1 annual supply from INA cascade.

        Uses per-FY schedule from SupplyCalculator when available.
        Falls back to the latest supply breakdown for unknown/future FYs.
        """
        if self._fy_supply is None:
            self._fy_supply = self.supply_calculator.get_supply_by_fy(
                apply_real_restrictions=self.apply_real_restrictions,
            )
        if fy is not None and fy in self._fy_supply:
            return self._fy_supply[fy]
        if self._annual_supply is None:
            breakdown = self.supply_calculator.get_supply_breakdown(
                apply_real_restrictions=self.apply_real_restrictions,
            )
            self._annual_supply = breakdown.india_eb1_supply
        return self._annual_supply

    def _estimate_ytd_consular(
        self, fy: int,
    ) -> tuple[int, int]:
        """Estimate YTD India EB-1 *consular* issuances for a FY from DOS data.

        DOS data is consular-only (not AOS). Since ~95 % of India EB-1
        issuance is AOS, this is informational only — not used for supply
        computations.  Returns (ytd_count, months_with_data).
        """
        try:
            self.supply_calculator._ensure_dos_loaded()
            dos_df = self.supply_calculator._dos_df
            if dos_df is None or dos_df.empty:
                return 0, 0

            eb1_india = dos_df[
                dos_df["visa_category"].isin(EB1_VISA_CATEGORIES)
                & dos_df["chargeability"].str.contains(
                    "India", case=False, na=False,
                )
            ]

            fy_counts: dict[int, int] = {}
            for _, row in eb1_india.iterrows():
                rm, ry = int(row["report_month"]), int(row["report_year"])
                if _fiscal_year(rm, ry) == fy:
                    fy_counts[rm] = fy_counts.get(rm, 0) + int(row["count"])

            return sum(fy_counts.values()), len(fy_counts)
        except Exception:
            return 0, 0

    # ── Demand curve ──────────────────────────────

    def _demand_at(self, year: int, month: int, raw: bool = False) -> int:
        """Cumulative demand with PD strictly before (year, month).

        Includes shadow demand: scales the I-485 inventory by the
        shadow ratio (I-485 + I-140 pipeline) / I-485 to account for
        approved I-140s who haven't filed I-485 yet.  As DOF advances,
        these become eligible to file, inflating the real demand curve.

        Args:
            raw: If True, return raw I-485 count without shadow scaling.
        """
        base = self.inventory.get_cumulative_demand(
            cutoff_year=year, cutoff_month=month,
            category=self._category_key,
        )
        if raw:
            return base
        return int(base * self._get_shadow_demand_ratio())

    def _total_demand(self) -> int:
        """Total effective demand including shadow I-140 pipeline (cached)."""
        if self._total_demand_cache is None:
            self._total_demand_cache = self._demand_at(2099, 1)
        return self._total_demand_cache

    def _total_demand_raw(self) -> int:
        """Total I-485 demand only (no shadow scaling)."""
        return self._demand_at(2099, 1, raw=True)

    # ── FAD binary search ─────────────────────────

    def _solve_fad(self, target_demand: float) -> tuple[date | None, int]:
        """Find FAD date where cumulative_demand(FAD) ≈ target_demand.

        Binary search over (year, month) ordinals with day-level
        interpolation within the crossing month.

        Returns:
            (fad_date, actual_demand_at_fad).
            fad_date is None if target exceeds total demand (→ Current).
        """
        total = self._total_demand()

        if target_demand >= total:
            return None, total
        if target_demand <= 0:
            return date(self._MIN_YEAR, 1, 1), 0

        # Ordinal: ord = year * 12 + month (month 1-indexed)
        lo = self._MIN_YEAR * 12 + 1
        hi = (self._MAX_YEAR + 1) * 12

        # Find first ordinal where demand >= target
        while lo < hi:
            mid = (lo + hi) // 2
            y = (mid - 1) // 12
            m = (mid - 1) % 12 + 1
            if self._demand_at(y, m) < target_demand:
                lo = mid + 1
            else:
                hi = mid

        # Demand at the crossing month and the one before
        y_hi = (lo - 1) // 12
        m_hi = (lo - 1) % 12 + 1
        demand_hi = self._demand_at(y_hi, m_hi)

        prev = lo - 1
        y_lo = (prev - 1) // 12
        m_lo = (prev - 1) % 12 + 1
        demand_lo = self._demand_at(y_lo, m_lo)

        # The FAD lies in the month *before* (y_hi, m_hi):
        #   demand_lo = PD < (y_lo, m_lo)
        #   demand_hi = PD < (y_hi, m_hi)
        # Cases between are in month (m_hi - 1) of y_hi.
        if m_hi == 1:
            fad_year, fad_month = y_hi - 1, 12
        else:
            fad_year, fad_month = y_hi, m_hi - 1

        # Day interpolation
        cases_in_month = demand_hi - demand_lo
        if cases_in_month > 0:
            fraction = (target_demand - demand_lo) / cases_in_month
        else:
            fraction = 0.5

        days_in_month = calendar.monthrange(fad_year, fad_month)[1]
        day = max(1, min(days_in_month, 1 + round(fraction * (days_in_month - 1))))

        try:
            fad = date(fad_year, fad_month, day)
        except ValueError:
            fad = date(fad_year, fad_month, min(day, 28))

        actual = int(demand_lo + cases_in_month * fraction)
        return fad, actual

    # ── Calibration ───────────────────────────────

    def calibrate(self) -> dict:
        """Compute materialization rate that reproduces the current VB FAD.

        Back-solves: rate = monthly_supply / demand_at_current_fad.
        Useful for grounding predictions in reality before forecasting.

        Returns dict with calibrated_rate and supporting data.
        """
        history = self.visa_bulletin.get_history()
        current_fad: Optional[date] = None
        for r in reversed(history):
            if r["fad"] is not None:
                current_fad = r["fad"]
                break

        if current_fad is None:
            return {
                "calibrated_rate": self.materialization_rate,
                "error": "No non-Current FAD in VB history",
            }

        # Interpolated demand at the actual FAD date
        demand_lo = self._demand_at(current_fad.year, current_fad.month)
        ny, nm = _next_cal_month(current_fad.year, current_fad.month)
        demand_hi = self._demand_at(ny, nm)

        days_in = calendar.monthrange(current_fad.year, current_fad.month)[1]
        day_frac = (current_fad.day - 1) / max(1, days_in - 1)
        interpolated = demand_lo + (demand_hi - demand_lo) * day_frac

        annual_supply = self._get_annual_supply()
        monthly_supply = annual_supply / 12.0

        calibrated = monthly_supply / interpolated if interpolated > 0 else self.materialization_rate

        shadow_ratio = self._get_shadow_demand_ratio()
        return {
            "current_fad": current_fad.isoformat(),
            "demand_at_fad": int(interpolated),
            "total_demand": self._total_demand(),
            "total_demand_i485_only": self._total_demand_raw(),
            "shadow_demand_ratio": round(shadow_ratio, 2),
            "annual_supply": annual_supply,
            "monthly_supply": round(monthly_supply, 1),
            "calibrated_rate": round(calibrated, 4),
            "current_rate": self.materialization_rate,
        }

    # ── Predictions ───────────────────────────────

    def predict_next_fad(
        self,
        bulletin_month: str | None = None,
        materialization_rate: float | None = None,
    ) -> dict:
        """Predict the next month's FAD.

        Args:
            bulletin_month: Target bulletin month ("2026-07").  If None,
                auto-detects from the latest VB entry + 1.
            materialization_rate: Override the instance rate for this call.

        Returns:
            Dict with predicted FAD, confidence bounds, methodology, and
            supporting demand/supply data.
        """
        rate = (
            materialization_rate if materialization_rate is not None
            else self.materialization_rate
        )

        # Determine target bulletin month
        history = self.visa_bulletin.get_history()
        if bulletin_month:
            parts = bulletin_month.split("-")
            bm_year, bm_month = int(parts[0]), int(parts[1])
        elif history:
            parts = history[-1]["bulletin_month"].split("-")
            bm_year, bm_month = _next_cal_month(int(parts[0]), int(parts[1]))
        else:
            return {"error": "No VB history available"}

        fy = _fiscal_year(bm_month, bm_year)
        annual_supply = self._get_annual_supply(fy)
        monthly_supply = annual_supply / 12.0

        # Solve for FAD at mid rate
        target = monthly_supply / rate
        fad, actual_demand = self._solve_fad(target)

        # Confidence bounds (relative to calibrated rate)
        rate_low = rate * self.RATE_BAND_LOW    # lower rate → bigger pool → later FAD
        rate_high = rate * self.RATE_BAND_HIGH  # higher rate → smaller pool → earlier FAD
        fad_low, _ = self._solve_fad(monthly_supply / rate_high)   # pessimistic (earlier)
        fad_high, _ = self._solve_fad(monthly_supply / rate_low)   # optimistic (later)

        # Current VB status for comparison
        current_fad: Optional[date] = None
        latest_bm_str: str | None = None
        if history:
            latest_bm_str = history[-1]["bulletin_month"]
            for r in reversed(history):
                if r["fad"] is not None:
                    current_fad = r["fad"]
                    break

        advancement_days: int | None = None
        if current_fad and fad:
            advancement_days = (fad - current_fad).days

        bm_str = f"{bm_year:04d}-{bm_month:02d}"
        total = self._total_demand()

        return {
            "bulletin_month": bm_str,
            "predicted_fad": fad.isoformat() if fad else None,
            "is_current": fad is None,
            "fad_low": fad_low.isoformat() if fad_low else None,
            "fad_high": fad_high.isoformat() if fad_high else None,
            "cumulative_demand": actual_demand,
            "target_monthly_supply": int(monthly_supply),
            "annual_supply": annual_supply,
            "materialization_rate": rate,
            "fiscal_year": fy,
            "current_fad": current_fad.isoformat() if current_fad else None,
            "latest_bulletin": latest_bm_str,
            "advancement_days": advancement_days,
            "total_demand": total,
            "methodology": (
                f"Oppenheim demand-supply matching: "
                f"target_monthly={int(monthly_supply):,} "
                f"(annual {annual_supply:,} / 12), "
                f"materialization_rate={rate:.2f}, "
                f"target_demand={int(target):,}. "
                f"Binary search over I-485 inventory "
                f"({total:,} total pending)."
            ),
        }

    def predict_trajectory(
        self,
        months_ahead: int = 12,
        materialization_rate: float | None = None,
    ) -> list[dict]:
        """Month-by-month FAD predictions.

        For each future month, solves for the FAD using the Oppenheim
        algorithm with accumulated issuance tracking.  As cases are
        issued, the eligible pool shrinks and the FAD must advance to
        bring in new cases.  At FY boundaries, supply updates from
        get_supply_by_fy().

        Args:
            months_ahead: Number of months to predict (default 12).
            materialization_rate: Override instance rate.

        Returns:
            List of prediction dicts, one per month.
        """
        rate = (
            materialization_rate if materialization_rate is not None
            else self.materialization_rate
        )

        history = self.visa_bulletin.get_history()
        if not history:
            return []

        parts = history[-1]["bulletin_month"].split("-")
        bm_year, bm_month = int(parts[0]), int(parts[1])

        results: list[dict] = []
        cumulative_issued: float = 0.0
        current_fy: int | None = None
        fy_issued_at_start: float = 0.0

        for _ in range(months_ahead):
            bm_year, bm_month = _next_cal_month(bm_year, bm_month)
            fy = _fiscal_year(bm_month, bm_year)

            # Track per-FY issuance for remaining_annual_supply
            if current_fy != fy:
                fy_issued_at_start = cumulative_issued
                current_fy = fy

            annual_supply = self._get_annual_supply(fy)
            monthly_supply = annual_supply / 12.0

            # Target demand = fresh pool needed + already-issued cases
            target = monthly_supply / rate + cumulative_issued
            fad, demand = self._solve_fad(target)

            # Confidence bounds (relative to calibrated rate)
            rate_low = rate * self.RATE_BAND_LOW
            rate_high = rate * self.RATE_BAND_HIGH
            fad_low, _ = self._solve_fad(
                monthly_supply / rate_high + cumulative_issued,
            )
            fad_high, _ = self._solve_fad(
                monthly_supply / rate_low + cumulative_issued,
            )

            fy_issued = cumulative_issued - fy_issued_at_start
            remaining = int(max(0, annual_supply - fy_issued - monthly_supply))

            results.append({
                "bulletin_month": f"{bm_year:04d}-{bm_month:02d}",
                "predicted_fad": fad.isoformat() if fad else None,
                "is_current": fad is None,
                "fad_low": fad_low.isoformat() if fad_low else None,
                "fad_high": fad_high.isoformat() if fad_high else None,
                "cumulative_demand": demand,
                "target_monthly_supply": int(monthly_supply),
                "materialization_rate": rate,
                "fiscal_year": fy,
                "remaining_annual_supply": remaining,
            })

            cumulative_issued += monthly_supply

        return results
