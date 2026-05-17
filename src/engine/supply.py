"""Centralized supply and spillover calculation logic.

This module eliminates the duplication that previously existed across the three
FastAPI route handlers. All INA 201/203 spillover math lives here.
"""

from dataclasses import dataclass
from typing import Optional

import pandas as pd

from ..parsers.dos_parser import DOSParser
from ..constants import (
    FB_STATUTORY_LIMIT,
    EB_BASE_LIMIT,
    EB1_STATUTORY_SHARE,
    EB45_STATUTORY_SHARE,
    DEFAULT_INDIA_EB1_SUPPLY,
    ACTUAL_RESTRICTED_COUNTRIES,
    EB45_CATEGORIES,
)
from .redistribution import RedistributionEngine


@dataclass
class SupplyBreakdown:
    """Complete breakdown of EB-1 supply components for a given scenario.

    NOTE on real_restrictions: When apply_real_restrictions=True (actual 2025-26
    policy, not the hypo freeze), real savings from ACTUAL_RESTRICTED_COUNTRIES
    are added *preferentially* only to india_eb1_supply (reflecting India's
    position as primary backlog beneficiary under INA 202(a)(5) surplus rules +
    real demand reduction from restricted countries). The freeze_* savings fields,
    total_eb_supply, and eb1_supply remain at standard/hypo values for backward
    compat and minimal shape change. Consumers should rely primarily on
    india_eb1_supply for India EB-1 predictions. This is intentional per research
    mandate for smallest diff / no return-shape changes.
    """

    eb_base_limit: int
    fb_spillover_std: int
    fb_savings_freeze: int
    eb45_spillover_std: int
    eb45_savings_freeze: int
    total_eb_supply: int
    eb1_supply: int
    india_eb1_supply: int  # effective supply available to India EB-1 (augmented by real_restrictions for current policy accuracy; see class docstring)


class SupplyCalculator:
    """
    Computes visa supply and spillover numbers.

    Centralizes the logic previously duplicated in api/main.py.
    """

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

    def get_supply_breakdown(self, apply_freeze: bool = False, apply_real_restrictions: bool = False) -> SupplyBreakdown:
        """Compute the full waterfall-style supply breakdown.
        apply_real_restrictions: Use ACTUAL_RESTRICTED_COUNTRIES from real 2025-2026
        Presidential Proclamations (distinct from hypothetical freeze).
        """
        self._ensure_dos_loaded()
        dos_parser = self.dos_parser

        eb_base = EB_BASE_LIMIT

        # Standard FB spillover (INA 201(c))
        total_fb_usage = dos_parser.get_total_fb_usage()
        standard_fb_spillover = max(0, FB_STATUTORY_LIMIT - total_fb_usage)

        fb_savings = 0
        eb45_savings = 0

        if apply_freeze:
            restricted = RedistributionEngine.get_default_restricted_list()
            engine = RedistributionEngine(restricted)

            # FB savings (spill to EB 1/2/3)
            fb_df = dos_parser.df[dos_parser.df['visa_category'].isin(DOSParser.FB_CATEGORIES)]
            fb_frozen = engine.apply_freeze(fb_df)
            fb_savings = engine.calculate_savings(fb_df, fb_frozen)

            # EB4/5 savings (spill only to EB-1)
            eb45_df = dos_parser.df[dos_parser.df['visa_category'].isin(EB45_CATEGORIES)]
            eb45_frozen = engine.apply_freeze(eb45_df)
            eb45_savings = engine.calculate_savings(eb45_df, eb45_frozen)

        # Real restrictions (actual policy, adds limited spillover on top of standard)
        real_fb_savings = 0
        real_eb45_savings = 0
        # Guard: real_restrictions only when not applying the (larger) hypothetical freeze.
        # Precedence: freeze takes priority as the "what-if" full scenario; real is additive
        # only to standard for current-world accuracy. Documented in Query params + here.
        if apply_real_restrictions and not apply_freeze:
            real_restricted = ACTUAL_RESTRICTED_COUNTRIES
            engine = RedistributionEngine(real_restricted)
            fb_df = dos_parser.df[dos_parser.df['visa_category'].isin(DOSParser.FB_CATEGORIES)]
            fb_frozen = engine.apply_freeze(fb_df)
            real_fb_savings = engine.calculate_savings(fb_df, fb_frozen)
            eb45_df = dos_parser.df[dos_parser.df['visa_category'].isin(EB45_CATEGORIES)]
            eb45_frozen = engine.apply_freeze(eb45_df)
            real_eb45_savings = engine.calculate_savings(eb45_df, eb45_frozen)

        # Standard EB4/5 spillover
        eb45_usage = dos_parser.df[dos_parser.df['visa_category'].isin(EB45_CATEGORIES)]['count'].sum()
        standard_eb45_spillover = max(0, int(EB_BASE_LIMIT * EB45_STATUTORY_SHARE) - eb45_usage)

        total_shared_supply = eb_base + standard_fb_spillover + fb_savings
        eb1_statutory_share = int(total_shared_supply * EB1_STATUTORY_SHARE)
        total_eb1_supply = eb1_statutory_share + standard_eb45_spillover + eb45_savings

        # Effective India EB-1 supply
        if not apply_freeze:
            india_eb1_supply = DEFAULT_INDIA_EB1_SUPPLY
            if apply_real_restrictions:
                # Real policy restrictions on listed countries reduce their FB/EB45 usage,
                # generating extra spillover to EB-1 (EB45 savings roll directly to EB-1;
                # FB savings contribute via shared pool). Add EB45 savings + conservative
                # share of FB savings to reflect India as primary backlog beneficiary.
                india_eb1_supply += real_eb45_savings + int(real_fb_savings * EB1_STATUTORY_SHARE)
        else:
            eb1_cats = ['E11', 'E12', 'E13', 'E1', 'IB1', 'IB2']
            row_eb1_usage = dos_parser.df[
                (~dos_parser.df['chargeability'].str.contains('India', case=False, na=False)) &
                (dos_parser.df['visa_category'].isin(eb1_cats))
            ]['count'].sum()
            india_eb1_supply = max(0, total_eb1_supply - row_eb1_usage)

        return SupplyBreakdown(
            eb_base_limit=eb_base,
            fb_spillover_std=standard_fb_spillover,
            fb_savings_freeze=fb_savings,
            eb45_spillover_std=standard_eb45_spillover,
            eb45_savings_freeze=eb45_savings,
            total_eb_supply=int(total_shared_supply + standard_eb45_spillover + eb45_savings),
            eb1_supply=int(total_eb1_supply),
            india_eb1_supply=int(india_eb1_supply),
        )
