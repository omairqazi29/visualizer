"""Centralized supply and spillover calculation logic.

Computes the full INA 201/203 cascade:
  Total EB pool (base + FB spillover) → EB-1 (28.6%) → + EB4/5 spillover
  → Total EB-1 worldwide → India EB-1 (portion, not all)

Key design decisions:
  - EB4/5 allocation uses the AUGMENTED pool (base + FB spillover), not just
    the base 140k. Per INA 203(b), each category gets its % of "worldwide level"
    which includes FB spillover per INA 201(d).
  - India does NOT get 100% of total EB-1. India gets its baseline (FY2024
    actual 6,952) plus a share of additional EB-1 from restrictions.
  - India's share of additional EB-1 = INDIA_OVERSUBSCRIBED_SHARE (default 80%),
    based on relative I-485 backlogs vs China (the other oversubscribed country).
  - DOS monthly data only captures consular IV issuances, NOT domestic AOS.
    EBs are AOS-heavy, so EB savings from restrictions are correctly small.
    The restrictions only block consular IVs (AOS hold vacated by Dorcas).
"""

from dataclasses import dataclass
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
    EB2_CATEGORIES,
    EB3_CATEGORIES,
)
from .redistribution import RedistributionEngine

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

    # Data-driven India share (computed from USCIS I-485 inventory)
    india_oversubscribed_share: float  # India EB-1 backlog / (India + China EB-1 backlogs)


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

    def get_supply_breakdown(self, apply_freeze: bool = False, apply_real_restrictions: bool = False) -> SupplyBreakdown:
        """Compute the full INA cascade: Total EB → EB-1 → India EB-1.

        Uses the AUGMENTED pool (base + FB spillover) for all category
        allocations per INA 203(b). EB4/5 spillover is the DELTA between
        restricted and baseline scenarios, not the raw savings amount.
        India gets INDIA_OVERSUBSCRIBED_SHARE (80%) of additional EB-1,
        not 100% — China is also oversubscribed.

        apply_real_restrictions: 91-country real policy (Proclamation + DOS IV pause).
        apply_freeze: Hypothetical freeze on DEFAULT_RESTRICTED_COUNTRIES.
        """
        self._ensure_dos_loaded()
        dos_parser = self.dos_parser

        eb_base = EB_BASE_LIMIT

        # --- Raw usage from DOS data ---
        total_fb_usage = dos_parser.get_total_fb_usage()
        eb45_usage = int(dos_parser.df[dos_parser.df['visa_category'].isin(EB45_CATEGORIES)]['count'].sum())

        # --- Savings from ALL categories ---
        fb_savings = 0
        eb1_savings = 0
        eb45_savings = 0
        eb23_savings = 0

        if apply_real_restrictions:
            restricted = ACTUAL_RESTRICTED_COUNTRIES
        elif apply_freeze:
            restricted = RedistributionEngine.get_default_restricted_list()
        else:
            restricted = None

        if restricted:
            engine = RedistributionEngine(restricted)

            fb_df = dos_parser.df[dos_parser.df['visa_category'].isin(DOSParser.FB_CATEGORIES)]
            fb_savings = engine.calculate_savings(fb_df, engine.apply_freeze(fb_df))

            eb1_df = dos_parser.df[dos_parser.df['visa_category'].isin(EB1_VISA_CATEGORIES)]
            eb1_savings = engine.calculate_savings(eb1_df, engine.apply_freeze(eb1_df))

            eb45_df = dos_parser.df[dos_parser.df['visa_category'].isin(EB45_CATEGORIES)]
            eb45_savings = engine.calculate_savings(eb45_df, engine.apply_freeze(eb45_df))

            eb23_cats = EB2_CATEGORIES + EB3_CATEGORIES
            eb23_df = dos_parser.df[dos_parser.df['visa_category'].isin(eb23_cats)]
            eb23_savings = engine.calculate_savings(eb23_df, engine.apply_freeze(eb23_df))

        # --- BASELINE cascade (no restrictions) ---
        fb_spill_base = max(0, FB_STATUTORY_LIMIT - total_fb_usage)
        pool_base = eb_base + fb_spill_base
        eb1_from_pool_base = int(pool_base * EB1_STATUTORY_SHARE)
        eb45_alloc_base = int(pool_base * EB45_STATUTORY_SHARE)
        eb45_spill_base = max(0, eb45_alloc_base - eb45_usage)
        total_eb1_base = eb1_from_pool_base + eb45_spill_base

        # --- CURRENT cascade (with restrictions if active) ---
        # FB spillover grows because restricted countries' FB usage is zeroed
        fb_spill_current = fb_spill_base + fb_savings
        pool_current = eb_base + fb_spill_current
        eb1_from_pool = int(pool_current * EB1_STATUTORY_SHARE)
        # EB4/5 allocation from AUGMENTED pool, usage reduced by savings
        eb45_alloc = int(pool_current * EB45_STATUTORY_SHARE)
        eb45_usage_effective = eb45_usage - eb45_savings
        eb45_spillover = max(0, eb45_alloc - eb45_usage_effective)
        total_eb1 = eb1_from_pool + eb45_spillover

        # --- India EB-1 ---
        india_baseline = DEFAULT_INDIA_EB1_SUPPLY  # 6,952 (FY2024 comprehensive)
        india_share = self.compute_india_share()

        if restricted:
            # Additional EB-1 supply from cascade change (NOT raw savings)
            additional_eb1 = total_eb1 - total_eb1_base
            # India absorbs freed EB-1 from restricted countries (most oversubscribed)
            # india_share computed from actual I-485 backlogs (India vs China).
            india_eb1 = india_baseline + eb1_savings + int(additional_eb1 * india_share)
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
            india_oversubscribed_share=india_share,
        )
