"""Domain policies for The Spillover Engine.

Full implementations of the three SpilloverPolicy strategies:
- StandardPolicy: no freeze, no restrictions (returns base values unchanged).
- FreezePolicy: hypothetical 75-country freeze using DEFAULT_RESTRICTED_COUNTRIES.
- RealRestrictionsPolicy: actual 2025-2026 Presidential Proclamation restrictions
  using ACTUAL_RESTRICTED_COUNTRIES.

Each policy encapsulates the FB/EB-4-5 savings computation and India EB-1 supply
adjustment previously scattered across boolean branches in SupplyCalculator.
"""

from __future__ import annotations

import pandas as pd

from .value_objects import PolicyName
from ..constants import (
    DEFAULT_RESTRICTED_COUNTRIES,
    ACTUAL_RESTRICTED_COUNTRIES,
    EB1_CATEGORIES,
    FB_CATEGORIES,
    EB45_CATEGORIES,
    EB1_STATUTORY_SHARE,
)
from ..engine.redistribution import apply_freeze_to_df, calculate_savings_from_freeze


class StandardPolicy:
    """Standard INA 201/203 spillover — no freeze, no restrictions."""

    name: PolicyName = PolicyName.STANDARD

    def compute_fb_savings(self, dos_df: pd.DataFrame) -> int:
        """No FB savings under standard policy."""
        return 0

    def compute_eb45_savings(self, dos_df: pd.DataFrame) -> int:
        """No EB-4/5 savings under standard policy."""
        return 0

    def adjust_india_eb1_supply(
        self,
        base_india_supply: int,
        fb_savings: int,
        eb45_savings: int,
        total_eb1_supply: int,
        dos_df: pd.DataFrame,
    ) -> int:
        """Return base India EB-1 supply unchanged."""
        return base_india_supply


class FreezePolicy:
    """Hypothetical 75-Country Freeze demand-curtailment scenario.

    Uses DEFAULT_RESTRICTED_COUNTRIES to zero out demand from restricted
    countries, then computes savings and redistributes to India EB-1.
    """

    name: PolicyName = PolicyName.FREEZE

    def compute_fb_savings(self, dos_df: pd.DataFrame) -> int:
        """Compute FB savings from freezing DEFAULT_RESTRICTED_COUNTRIES."""
        fb_df = dos_df[dos_df['visa_category'].isin(FB_CATEGORIES)]
        frozen = apply_freeze_to_df(fb_df, DEFAULT_RESTRICTED_COUNTRIES)
        return calculate_savings_from_freeze(fb_df, frozen)

    def compute_eb45_savings(self, dos_df: pd.DataFrame) -> int:
        """Compute EB-4/5 savings from freezing DEFAULT_RESTRICTED_COUNTRIES."""
        eb45_df = dos_df[dos_df['visa_category'].isin(EB45_CATEGORIES)]
        frozen = apply_freeze_to_df(eb45_df, DEFAULT_RESTRICTED_COUNTRIES)
        return calculate_savings_from_freeze(eb45_df, frozen)

    def adjust_india_eb1_supply(
        self,
        base_india_supply: int,
        fb_savings: int,
        eb45_savings: int,
        total_eb1_supply: int,
        dos_df: pd.DataFrame,
    ) -> int:
        """Under freeze, India gets total EB-1 supply minus non-India EB-1 usage."""
        # base_india_supply, fb_savings, eb45_savings unused — freeze path
        # derives India supply from total_eb1_supply minus non-India EB-1 usage.
        non_india_eb1_usage = dos_df[
            (~dos_df['chargeability'].str.contains('India', case=False, na=False))
            & (dos_df['visa_category'].isin(EB1_CATEGORIES))
        ]['count'].sum()
        return max(0, total_eb1_supply - int(non_india_eb1_usage))


class RealRestrictionsPolicy:
    """Actual 2025-2026 Presidential Proclamation restrictions.

    Uses ACTUAL_RESTRICTED_COUNTRIES. Savings are added preferentially to
    India EB-1 supply (EB-4/5 savings directly, FB savings via EB-1 share).
    """

    name: PolicyName = PolicyName.REAL_RESTRICTIONS

    def compute_fb_savings(self, dos_df: pd.DataFrame) -> int:
        """Compute FB savings from actual restricted countries."""
        fb_df = dos_df[dos_df['visa_category'].isin(FB_CATEGORIES)]
        frozen = apply_freeze_to_df(fb_df, ACTUAL_RESTRICTED_COUNTRIES)
        return calculate_savings_from_freeze(fb_df, frozen)

    def compute_eb45_savings(self, dos_df: pd.DataFrame) -> int:
        """Compute EB-4/5 savings from actual restricted countries."""
        eb45_df = dos_df[dos_df['visa_category'].isin(EB45_CATEGORIES)]
        frozen = apply_freeze_to_df(eb45_df, ACTUAL_RESTRICTED_COUNTRIES)
        return calculate_savings_from_freeze(eb45_df, frozen)

    def adjust_india_eb1_supply(
        self,
        base_india_supply: int,
        fb_savings: int,
        eb45_savings: int,
        total_eb1_supply: int,
        dos_df: pd.DataFrame,
    ) -> int:
        """Add real savings to India base: EB-4/5 savings + EB-1 share of FB savings."""
        return max(0, base_india_supply + eb45_savings + int(fb_savings * EB1_STATUTORY_SHARE))
