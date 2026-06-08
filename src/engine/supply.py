"""Centralized supply and spillover calculation logic.

Computes the full INA 201/203 cascade:
  Total EB pool (base + FB spillover) → EB-1 (28.6%) → + EB4/5 spillover
  → Total EB-1 worldwide → India EB-1 (portion, not all)

Key design decisions:
  - EB4/5 allocation uses the AUGMENTED pool (base + FB spillover), not just
    the base 140k. Per INA 203(b), each category gets its % of "worldwide level"
    which includes FB spillover per INA 201(d).
  - India does NOT get 100% of total EB-1. India EB-1 is computed by subtracting
    data-driven non-India demand from total EB-1 supply. Non-India demand is
    derived from DHS Yearbook data (dhs_eb_category_usage.csv) and live USCIS
    I-485 inventory data.
  - EB-4/5 spillover uses TOTAL usage (consular + AOS) from DHS Yearbook, not
    DOS consular-only data. AOS is unaffected by travel bans (Dorcas ruling
    vacated USCIS adjudicative hold). Only consular savings from restricted
    countries reduce effective EB-4/5 usage.
  - SIV categories (SQ/SI/SD/SE/SK/SR/SU/SW) are EXCLUDED from EB-4/5
    restriction savings. Afghan/Iraqi SIVs are congressionally mandated under
    the Afghan Allies Protection Act and exempt from Proclamation entry bans
    and public charge IV pauses. DOS data confirms continued issuance.
  - DOS monthly data only captures consular IV issuances, NOT domestic AOS.
    FB is consular-heavy so FB savings are reliable. EB savings are small
    because EBs are AOS-heavy (correctly captured).

Data sources (all auto-loaded from data/ files, no hardcoded numbers):
  - DHS Yearbook: data/DHS_Yearbook/dhs_eb_category_usage.csv
  - USCIS I-485 Inventory: data/eb_inventory_*.xlsx (auto-discovered)
  - DOS Consular IV: data/DOS/*.xlsx (load_from_directory)
  - India EB-1 Historical: INDIA_EB1_HISTORICAL (Report of the Visa Office)
"""

import csv
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Optional

import pandas as pd

from ..parsers.dos_parser import DOSParser
from ..parsers.inventory_parser import InventoryParser
from ..constants import (
    FB_STATUTORY_LIMIT,
    EB_BASE_LIMIT,
    EB1_STATUTORY_SHARE,
    EB45_STATUTORY_SHARE,
    ACTUAL_RESTRICTED_COUNTRIES,
    DEFAULT_INDIA_EB1_SUPPLY,
    INDIA_OVERSUBSCRIBED_SHARE,
    EB45_CATEGORIES,
    EB45_NON_SIV_CATEGORIES,
    EB2_CATEGORIES,
    EB3_CATEGORIES,
)
from .redistribution import RedistributionEngine

# Historical India EB-1 actuals from Report of the Visa Office, Table V Part 2
# (travel.state.gov). Total EB-1 charged to India: principals + derivatives,
# consular IV issuances + USCIS adjustments of status.
# Used as baseline supply for FYs where we don't have monthly DOS data.
INDIA_EB1_HISTORICAL: dict[int, int] = {
    2015: 12_253,  # FY2015 Report of the Visa Office
    2016: 10_985,  # FY2016 Report of the Visa Office
    2017: 13_082,  # FY2017 Report of the Visa Office
    2018: 10_967,  # FY2018 Report of the Visa Office (cited in CRS R47164)
    2019: 9_008,   # FY2019 Report of the Visa Office (cited in CRS R47164)
    2020: 17_014,  # FY2020 — COVID FB spillover began inflating EB ceiling
    2021: 30_825,  # FY2021 — peak year, ~262k total EB ceiling from FB underuse
    2022: 21_437,  # FY2022 — still elevated (~280k EB), FB resuming
    2023: 16_604,  # FY2023 — EB ceiling ~197k, India EB-1 retrogressed mid-year
    2024: 6_952,   # FY2024 — EB ceiling back to ~140k baseline
}


# ---------------------------------------------------------------------------
# DHS Yearbook loader: reads data/DHS_Yearbook/dhs_eb_category_usage.csv
# Generated from actual DHS Yearbook XLSX files (Table 7 / LIAR Table 1B).
# Columns: fiscal_year, category, total, aos, consular
# ---------------------------------------------------------------------------
_DHS_CSV_PATH = "data/DHS_Yearbook/dhs_eb_category_usage.csv"


@lru_cache(maxsize=1)
def _load_dhs_eb_data(csv_path: str = _DHS_CSV_PATH) -> list[dict]:
    """Load DHS Yearbook EB category usage from CSV.

    Returns list of dicts with keys: fiscal_year, category, total, aos, consular.
    Empty list if file not found (callers fall back to hardcoded defaults).
    """
    try:
        with open(csv_path, newline="") as f:
            return list(csv.DictReader(f))
    except FileNotFoundError:
        return []


def _get_dhs_eb45_total(csv_path: str = _DHS_CSV_PATH) -> dict[int, int]:
    """EB-4 + EB-5 TOTAL usage (consular + AOS) by FY from DHS Yearbook.

    DOS data is consular-only; AOS is the majority of EB-4/5 and is
    UNAFFECTED by travel bans (Dorcas v. USCIS vacated hold).
    """
    rows = _load_dhs_eb_data(csv_path)
    result: dict[int, int] = {}
    for r in rows:
        cat = r["category"]
        if cat in ("EB4", "EB5"):
            fy = int(r["fiscal_year"])
            result[fy] = result.get(fy, 0) + int(r["total"])
    return result


def _get_dhs_eb45_aos(csv_path: str = _DHS_CSV_PATH) -> dict[int, int]:
    """EB-4/5 AOS-only portion by FY. AOS is unaffected by consular restrictions."""
    rows = _load_dhs_eb_data(csv_path)
    result: dict[int, int] = {}
    for r in rows:
        cat = r["category"]
        if cat in ("EB4", "EB5") and r.get("aos"):
            fy = int(r["fiscal_year"])
            result[fy] = result.get(fy, 0) + int(r["aos"])
    return result


def _get_dhs_eb1_worldwide(csv_path: str = _DHS_CSV_PATH) -> dict[int, int]:
    """Total EB-1 worldwide usage (consular + AOS) by FY from DHS Yearbook."""
    rows = _load_dhs_eb_data(csv_path)
    return {
        int(r["fiscal_year"]): int(r["total"])
        for r in rows
        if r["category"] == "EB1"
    }


def _compute_non_india_eb1_demand(csv_path: str = _DHS_CSV_PATH) -> dict[int, int]:
    """Non-India EB-1 demand by FY = DHS total EB-1 − India EB-1 historical.

    Data-driven from actual DHS Yearbook and Report of the Visa Office data.
    """
    eb1_ww = _get_dhs_eb1_worldwide(csv_path)
    return {
        fy: total - INDIA_EB1_HISTORICAL.get(fy, 0)
        for fy, total in eb1_ww.items()
        if fy in INDIA_EB1_HISTORICAL
    }

# EB-1 visa category codes (DOS consular IV symbols).
EB1_VISA_CATEGORIES: list[str] = ['E11', 'E12', 'E13', 'E1', 'IB1', 'IB2']


@dataclass
class SupplyBreakdown:
    """Full INA cascade: Total EB → EB-1 → India EB-1.

    Shows the complete statutory waterfall so the frontend can render
    Total EB pool, EB-1 worldwide, and India's portion separately.
    India does NOT get 100% of EB-1 — see non_india_eb1.
    """

    # Full INA cascade (system-wide)
    eb_base_limit: int              # INA 203(b) base: 140,000
    fb_spillover: int               # FB→EB spillover (total, includes savings)
    total_eb_pool: int              # base + fb_spillover
    eb1_from_pool: int              # 28.6% of total_eb_pool
    eb45_spillover: int             # Unused EB4/5 → EB-1 (from augmented pool)
    total_eb1: int                  # Worldwide EB-1 = eb1_from_pool + eb45_spillover

    # India EB-1
    india_eb1_baseline: int         # FY2024 actual: 6,952 (consular + I-485)
    india_eb1_supply: int           # Baseline + share of additional from restrictions
    non_india_eb1: int              # total_eb1 - india_eb1_supply

    # Savings from restricted countries (all 0 under baseline)
    fb_savings: int                 # FB from restricted (consular)
    eb1_savings: int                # EB-1 from restricted (consular, small — EBs are AOS-heavy)
    eb45_savings: int               # EB4/5 from restricted (raw usage, for context)
    eb23_savings: int               # EB-2/3 from restricted (context, stays in EB-2/3)

    # Per-country savings breakdown (empty dicts under baseline)
    fb_savings_by_country: dict[str, int]
    eb1_savings_by_country: dict[str, int]
    eb45_savings_by_country: dict[str, int]
    eb23_savings_by_country: dict[str, int]

    # Data-driven inputs (from DHS Yearbook / I-485 inventory)
    india_oversubscribed_share: float  # Informational: India/(India+China) from I-485 inventory
    non_india_eb1_demand: int          # DHS-derived non-India annual EB-1 consumption
    eb45_total_usage: int              # DHS Yearbook total EB-4/5 (consular + AOS)


class SupplyCalculator:
    """Computes visa supply and spillover numbers from DOS data."""

    def __init__(self, dos_dir: str = "data/DOS"):
        self.dos_dir = dos_dir
        self._dos_df: Optional[pd.DataFrame] = None
        self._dos_parser: Optional[DOSParser] = None

    def _ensure_dos_loaded(self) -> None:
        if self._dos_df is None:
            self._dos_df = DOSParser.load_from_directory(self.dos_dir)
            self._dos_parser = DOSParser(self.dos_dir)
            self._dos_parser.df = self._dos_df

    @property
    def dos_parser(self) -> DOSParser:
        self._ensure_dos_loaded()
        assert self._dos_parser is not None
        return self._dos_parser

    @staticmethod
    def compute_india_share() -> float:
        """Compute India's share of oversubscribed EB-1 from actual I-485 inventory.

        Uses the USCIS EB I-485 inventory to get India and China EB-1 pending
        counts (with dependents). India's share = India / (India + China).
        Falls back to the hardcoded INDIA_OVERSUBSCRIBED_SHARE if data unavailable.

        NOTE: This is now informational only. The supply model uses
        non-India demand subtraction (from DHS Yearbook) instead.
        """
        try:
            inv = InventoryParser.latest()
            backlogs = inv.get_all_eb1_backlogs()
            india = backlogs.get("India", 0)
            china = backlogs.get("China", 0)
            if india + china == 0:
                return INDIA_OVERSUBSCRIBED_SHARE
            return india / (india + china)
        except Exception:
            return INDIA_OVERSUBSCRIBED_SHARE

    @staticmethod
    def _get_eb45_total_baseline() -> int:
        """Total EB-4/5 annual usage (consular + AOS) from latest DHS Yearbook CSV.

        DOS data is consular-only; AOS is the majority of EB-4/5.
        Using consular alone massively understates real usage and
        inflates the EB-4/5 → EB-1 spillover.
        """
        data = _get_dhs_eb45_total()
        if data:
            return data[max(data)]
        return 26_530  # fallback if CSV missing

    @staticmethod
    def _get_eb45_aos_baseline() -> int:
        """EB-4/5 AOS-only usage — unaffected by consular restrictions.

        Travel bans and IV pauses only block consular processing.
        AOS continues (Dorcas v. USCIS vacated adjudicative hold).
        """
        data = _get_dhs_eb45_aos()
        if data:
            return data[max(data)]
        return 14_460  # fallback if CSV missing

    @staticmethod
    def _get_non_india_eb1_demand() -> int:
        """Data-driven non-India EB-1 annual demand.

        Primary: live USCIS I-485 inventory (non-India EB-1 pending = their
        annual throughput proxy, since ROW is Current and processes quickly).
        Fallback: DHS Yearbook average of baseline FYs (2023-2024).
        """
        # Try live inventory data first — reflects current conditions
        try:
            inv = InventoryParser.latest()
            backlogs = inv.get_all_eb1_backlogs()
            non_india = sum(
                v for k, v in backlogs.items() if k != "India"
            )
            if non_india > 0:
                return non_india
        except Exception:
            pass

        # Fallback: DHS Yearbook (avg of most recent baseline FYs)
        historical = _compute_non_india_eb1_demand()
        recent = {k: v for k, v in historical.items() if k >= 2023}
        if recent:
            return int(sum(recent.values()) / len(recent))
        return 40_510  # last-resort fallback

    def get_supply_breakdown(self, apply_freeze: bool = False, apply_real_restrictions: bool = False) -> SupplyBreakdown:
        """Compute the full INA cascade: Total EB → EB-1 → India EB-1.

        Uses the AUGMENTED pool (base + FB spillover) for all category
        allocations per INA 203(b). EB4/5 spillover is the DELTA between
        restricted and baseline scenarios, not the raw savings amount.
        India gets INDIA_OVERSUBSCRIBED_SHARE (80%) of additional EB-1,
        not 100% — China is also oversubscribed.

        apply_real_restrictions: 91-country real policy (Proclamation + DOS IV pause).
        apply_freeze: Hypothetical freeze on DEFAULT_RESTRICTED_COUNTRIES.

        Note: This method uses only the LATEST fiscal year's DOS data for
        usage and savings calculations.  Statutory limits (226K FB, 140K EB)
        are annual, so mixing multiple FYs would inflate numbers.
        For per-FY supply breakdowns, use get_supply_by_fy() instead.
        """
        self._ensure_dos_loaded()
        dos_parser = self.dos_parser

        eb_base = EB_BASE_LIMIT

        # --- Scope to latest FY for annual statutory comparison ---
        available_fys = dos_parser.get_available_fys()
        if available_fys:
            latest_fy = max(available_fys)
            fy_df = self._filter_fy(dos_parser.df, latest_fy)
        else:
            fy_df = dos_parser.df

        # --- Raw usage from latest FY DOS data ---
        total_fb_usage = int(fy_df[fy_df['visa_category'].isin(DOSParser.FB_CATEGORIES)]['count'].sum())
        # EB-4/5: DOS is consular-only; use DHS Yearbook for TOTAL (consular+AOS)
        eb45_consular = int(fy_df[fy_df['visa_category'].isin(EB45_CATEGORIES)]['count'].sum())
        eb45_total_baseline = self._get_eb45_total_baseline()
        eb45_aos = self._get_eb45_aos_baseline()

        # --- Savings from ALL categories ---
        fb_savings = 0
        eb1_savings = 0
        eb45_savings = 0
        eb23_savings = 0
        fb_savings_by_country: dict[str, int] = {}
        eb1_savings_by_country: dict[str, int] = {}
        eb45_savings_by_country: dict[str, int] = {}
        eb23_savings_by_country: dict[str, int] = {}

        if apply_real_restrictions:
            restricted = ACTUAL_RESTRICTED_COUNTRIES
        elif apply_freeze:
            restricted = RedistributionEngine.get_default_restricted_list()
        else:
            restricted = None

        if restricted:
            engine = RedistributionEngine(restricted)

            fb_df = fy_df[fy_df['visa_category'].isin(DOSParser.FB_CATEGORIES)]
            fb_frozen = engine.apply_freeze(fb_df)
            fb_savings = engine.calculate_savings(fb_df, fb_frozen)
            fb_savings_by_country = engine.calculate_savings_by_country(fb_df, fb_frozen)

            eb1_df = fy_df[fy_df['visa_category'].isin(EB1_VISA_CATEGORIES)]
            eb1_frozen = engine.apply_freeze(eb1_df)
            eb1_savings = engine.calculate_savings(eb1_df, eb1_frozen)
            eb1_savings_by_country = engine.calculate_savings_by_country(eb1_df, eb1_frozen)

            # EB-4/5 savings: exclude SIV categories (congressionally mandated,
            # exempt from executive restrictions — continue being issued).
            eb45_nonsiv_df = fy_df[fy_df['visa_category'].isin(EB45_NON_SIV_CATEGORIES)]
            eb45_nonsiv_frozen = engine.apply_freeze(eb45_nonsiv_df)
            eb45_savings = engine.calculate_savings(eb45_nonsiv_df, eb45_nonsiv_frozen)
            eb45_savings_by_country = engine.calculate_savings_by_country(eb45_nonsiv_df, eb45_nonsiv_frozen)

            eb23_cats = EB2_CATEGORIES + EB3_CATEGORIES
            eb23_df = fy_df[fy_df['visa_category'].isin(eb23_cats)]
            eb23_frozen = engine.apply_freeze(eb23_df)
            eb23_savings = engine.calculate_savings(eb23_df, eb23_frozen)
            eb23_savings_by_country = engine.calculate_savings_by_country(eb23_df, eb23_frozen)

        # --- BASELINE cascade (no restrictions) ---
        fb_spill_base = max(0, FB_STATUTORY_LIMIT - total_fb_usage)
        pool_base = eb_base + fb_spill_base
        eb1_from_pool_base = int(pool_base * EB1_STATUTORY_SHARE)
        # EB-4/5 spillover uses TOTAL usage (DHS Yearbook), not consular-only
        eb45_alloc_base = int(pool_base * EB45_STATUTORY_SHARE)
        eb45_spill_base = max(0, eb45_alloc_base - eb45_total_baseline)
        total_eb1_base = eb1_from_pool_base + eb45_spill_base

        # --- CURRENT cascade (with restrictions if active) ---
        # FB spillover grows because restricted countries' FB usage is zeroed
        fb_spill_current = fb_spill_base + fb_savings
        pool_current = eb_base + fb_spill_current
        eb1_from_pool = int(pool_current * EB1_STATUTORY_SHARE)
        # EB-4/5: restrictions only block CONSULAR; AOS continues unaffected.
        # Effective usage = AOS (unchanged) + remaining consular after savings.
        eb45_alloc = int(pool_current * EB45_STATUTORY_SHARE)
        eb45_consular_effective = max(0, eb45_consular - eb45_savings)
        eb45_total_effective = eb45_aos + eb45_consular_effective
        eb45_spillover = max(0, eb45_alloc - eb45_total_effective)
        total_eb1 = eb1_from_pool + eb45_spillover

        # --- India EB-1 ---
        india_baseline = DEFAULT_INDIA_EB1_SUPPLY  # 6,952 (FY2024 comprehensive)
        india_share = self.compute_india_share()  # informational
        non_india_demand = self._get_non_india_eb1_demand()

        if restricted:
            # Data-driven: India = total EB-1 − non-India demand.
            # Non-India demand from DHS Yearbook (stable ~40k in FY2023-2024).
            # eb1_savings reduce non-India demand (restricted countries' consular
            # EB-1 usage is zeroed, freeing those numbers).
            non_india_effective = non_india_demand - eb1_savings
            india_eb1 = max(india_baseline, total_eb1 - non_india_effective)
        else:
            india_eb1 = india_baseline

        non_india = max(0, total_eb1 - india_eb1)

        return SupplyBreakdown(
            eb_base_limit=eb_base,
            fb_spillover=fb_spill_current,
            total_eb_pool=pool_current,
            eb1_from_pool=eb1_from_pool,
            eb45_spillover=eb45_spillover,
            total_eb1=total_eb1,
            india_eb1_baseline=india_baseline,
            india_eb1_supply=india_eb1,
            non_india_eb1=non_india,
            fb_savings=fb_savings,
            eb1_savings=eb1_savings,
            eb45_savings=eb45_savings,
            eb23_savings=eb23_savings,
            fb_savings_by_country=fb_savings_by_country,
            eb1_savings_by_country=eb1_savings_by_country,
            eb45_savings_by_country=eb45_savings_by_country,
            eb23_savings_by_country=eb23_savings_by_country,
            india_oversubscribed_share=india_share,
            non_india_eb1_demand=non_india_demand,
            eb45_total_usage=eb45_total_baseline,
        )

    def get_supply_by_fy(
        self, apply_freeze: bool = False, apply_real_restrictions: bool = False
    ) -> dict[int, int]:
        """Compute India EB-1 supply per fiscal year from available DOS data.

        Runs the full INA cascade per FY using actual FB/EB usage data.
        For FYs without DOS data, uses INDIA_EB1_HISTORICAL if available,
        otherwise falls back to the latest computed FY.

        Returns {fy_year: india_eb1_supply}.
        """
        self._ensure_dos_loaded()
        dos = self.dos_parser

        # Determine which FYs have data
        available_fys = dos.get_available_fys()
        if not available_fys:
            breakdown = self.get_supply_breakdown(apply_freeze, apply_real_restrictions)
            return {2025: breakdown.india_eb1_supply}

        # Per-FY FB and EB4/5 consular usage (DOS data)
        fb_by_fy = dos.get_fb_usage_by_fy()
        eb45_consular_by_fy = dos.get_usage_by_fy(EB45_CATEGORIES)

        india_baseline = DEFAULT_INDIA_EB1_SUPPLY
        non_india_demand = self._get_non_india_eb1_demand()
        eb45_total_baseline = self._get_eb45_total_baseline()
        eb45_aos = self._get_eb45_aos_baseline()

        # Determine restricted set
        if apply_real_restrictions:
            restricted = ACTUAL_RESTRICTED_COUNTRIES
        elif apply_freeze:
            restricted = RedistributionEngine.get_default_restricted_list()
        else:
            restricted = None

        # Restrictions took effect during FY2025 (Proclamation 10949, June 2025).
        # Do not apply restrictions retroactively to earlier fiscal years —
        # computing hypothetical savings on pre-restriction data is nonsensical.
        _RESTRICTION_EFFECTIVE_FY = 2025

        # Pre-compute per-FY savings if restrictions active (only FYs >= effective year)
        fy_fb_savings: dict[int, int] = {}
        fy_eb1_savings: dict[int, int] = {}
        fy_eb45_savings: dict[int, int] = {}
        if restricted:
            engine = RedistributionEngine(restricted)
            for fy in available_fys:
                if fy < _RESTRICTION_EFFECTIVE_FY:
                    continue
                fy_df = self._filter_fy(dos.df, fy)
                fb_df = fy_df[fy_df["visa_category"].isin(DOSParser.FB_CATEGORIES)]
                fy_fb_savings[fy] = engine.calculate_savings(fb_df, engine.apply_freeze(fb_df))
                eb1_df = fy_df[fy_df["visa_category"].isin(EB1_VISA_CATEGORIES)]
                fy_eb1_savings[fy] = engine.calculate_savings(eb1_df, engine.apply_freeze(eb1_df))
                # Exclude SIV from EB-4/5 savings (exempt from restrictions)
                eb45_nonsiv = fy_df[fy_df["visa_category"].isin(EB45_NON_SIV_CATEGORIES)]
                fy_eb45_savings[fy] = engine.calculate_savings(eb45_nonsiv, engine.apply_freeze(eb45_nonsiv))

        result: dict[int, int] = {}
        for fy in available_fys:
            # Pre-restriction FYs: use actual historical data (Report of the
            # Visa Office) or baseline constant — never apply restrictions.
            if fy < _RESTRICTION_EFFECTIVE_FY:
                result[fy] = INDIA_EB1_HISTORICAL.get(fy, india_baseline)
                continue

            fb_usage = fb_by_fy.get(fy, 0)
            eb45_consular = eb45_consular_by_fy.get(fy, 0)

            # Baseline cascade (EB-4/5 uses DHS Yearbook total, not consular)
            fb_spill_base = max(0, FB_STATUTORY_LIMIT - fb_usage)
            pool_base = EB_BASE_LIMIT + fb_spill_base
            eb1_base = int(pool_base * EB1_STATUTORY_SHARE)
            eb45_alloc_base = int(pool_base * EB45_STATUTORY_SHARE)
            eb45_spill_base = max(0, eb45_alloc_base - eb45_total_baseline)
            total_eb1_base = eb1_base + eb45_spill_base

            if restricted:
                fb_sav = fy_fb_savings.get(fy, 0)
                eb1_sav = fy_eb1_savings.get(fy, 0)
                eb45_sav = fy_eb45_savings.get(fy, 0)

                fb_spill = fb_spill_base + fb_sav
                pool = EB_BASE_LIMIT + fb_spill
                eb1_from_pool = int(pool * EB1_STATUTORY_SHARE)
                eb45_alloc = int(pool * EB45_STATUTORY_SHARE)
                # Restrictions only reduce consular; AOS unaffected
                eb45_effective = eb45_aos + max(0, eb45_consular - eb45_sav)
                eb45_spill = max(0, eb45_alloc - eb45_effective)
                total_eb1 = eb1_from_pool + eb45_spill
                # India = total − non-India demand (data-driven subtraction)
                non_india_eff = non_india_demand - eb1_sav
                india_eb1 = max(india_baseline, total_eb1 - non_india_eff)
            else:
                india_eb1 = india_baseline

            result[fy] = india_eb1

        # Include known historical FYs not in DOS data
        for fy, supply in INDIA_EB1_HISTORICAL.items():
            if fy not in result:
                result[fy] = supply

        return dict(sorted(result.items()))

    @staticmethod
    def _filter_fy(df: pd.DataFrame, fy: int) -> pd.DataFrame:
        """Filter DataFrame rows belonging to a specific fiscal year."""
        mask = df.apply(
            lambda r: DOSParser._assign_fy(int(r["report_month"]), int(r["report_year"])) == fy,
            axis=1,
        )
        return df[mask]
