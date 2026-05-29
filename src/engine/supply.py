"""Centralized supply and spillover calculation logic.

This module eliminates the duplication that previously existed across the three
FastAPI route handlers. All INA 201/203 spillover math lives here.

Supports dependency injection of loader and policy via the Strategy pattern.
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
    EB45_CATEGORIES,
)

# Deferred imports to avoid circular dependency:
# domain.policies → engine.redistribution → engine.__init__ → engine.supply
# Import lazily in methods / __init__ instead of at module level.


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
    Accepts optional dependency injection for loader and policy while
    preserving full backward compatibility.
    """

    def __init__(
        self,
        dos_loader=None,
        policy=None,
        dos_dir: str = "data/DOS",
    ):
        from ..adapters.pandas_dos_loader import PandasDOSLoader
        from ..domain.policies import StandardPolicy

        self.dos_dir = dos_dir
        self._loader = dos_loader or PandasDOSLoader(dos_dir)
        self._default_policy = policy or StandardPolicy()
        self._dos_df: Optional[pd.DataFrame] = None
        self._dos_parser: Optional[DOSParser] = None

    def _ensure_dos_loaded(self) -> None:
        if self._dos_df is None:
            self._dos_df = self._loader.load_all_issuances()
            # Shim: DOSParser is used only for get_total_fb_usage() and
            # get_monthly_distribution() which read self.df — the file_path
            # arg (dos_dir) is never used for I/O.  Do NOT call load_data()
            # or parse() on this instance.
            self._dos_parser = DOSParser(self.dos_dir)
            self._dos_parser.df = self._dos_df

    @property
    def dos_parser(self) -> DOSParser:
        self._ensure_dos_loaded()
        assert self._dos_parser is not None
        return self._dos_parser

    def get_monthly_distribution(
        self, country: str | None = None, categories: list[str] | None = None
    ) -> dict:
        """Get historical monthly issuance distribution.

        Provides clean access to monthly distribution data without
        requiring callers to access the internal dos_parser property.
        """
        self._ensure_dos_loaded()
        assert self._dos_parser is not None
        return self._dos_parser.get_monthly_distribution(
            country=country, categories=categories
        )

    def _resolve_policy(self, policy_name: str):
        """Map a policy name string to a SpilloverPolicy instance."""
        from ..domain.policies import StandardPolicy, FreezePolicy, RealRestrictionsPolicy
        from ..domain.value_objects import PolicyName

        policy_map = {
            PolicyName.STANDARD.value: StandardPolicy,
            PolicyName.FREEZE.value: FreezePolicy,
            PolicyName.REAL_RESTRICTIONS.value: RealRestrictionsPolicy,
        }
        policy_cls = policy_map.get(policy_name)
        if policy_cls is None:
            raise ValueError(f"Unknown policy: {policy_name}")
        return policy_cls()

    def _compute_with_policy(self, policy) -> SupplyBreakdown:
        """Compute supply breakdown using the injected policy strategy."""
        from ..domain.value_objects import PolicyName

        assert self._dos_df is not None
        dos_df = self._dos_df
        dos_parser = self.dos_parser

        eb_base = EB_BASE_LIMIT

        # Standard FB spillover (INA 201(c))
        total_fb_usage = dos_parser.get_total_fb_usage()
        standard_fb_spillover = max(0, FB_STATUTORY_LIMIT - total_fb_usage)

        # Policy-specific savings
        fb_savings = policy.compute_fb_savings(dos_df)
        eb45_savings = policy.compute_eb45_savings(dos_df)

        # Only freeze savings affect aggregate supply numbers;
        # real_restrictions savings only affect india_eb1_supply via adjust.
        if policy.name == PolicyName.FREEZE:
            report_fb_savings = fb_savings
            report_eb45_savings = eb45_savings
        else:
            report_fb_savings = 0
            report_eb45_savings = 0

        # Standard EB4/5 spillover
        eb45_usage = dos_df[dos_df['visa_category'].isin(EB45_CATEGORIES)]['count'].sum()
        standard_eb45_spillover = max(0, int(EB_BASE_LIMIT * EB45_STATUTORY_SHARE) - eb45_usage)

        total_shared_supply = eb_base + standard_fb_spillover + report_fb_savings
        eb1_statutory_share = int(total_shared_supply * EB1_STATUTORY_SHARE)
        total_eb1_supply = eb1_statutory_share + standard_eb45_spillover + report_eb45_savings

        india_eb1_supply = policy.adjust_india_eb1_supply(
            DEFAULT_INDIA_EB1_SUPPLY, fb_savings, eb45_savings, total_eb1_supply, dos_df
        )

        return SupplyBreakdown(
            eb_base_limit=eb_base,
            fb_spillover_std=standard_fb_spillover,
            fb_savings_freeze=report_fb_savings,
            eb45_spillover_std=standard_eb45_spillover,
            eb45_savings_freeze=report_eb45_savings,
            total_eb_supply=int(total_shared_supply + standard_eb45_spillover + report_eb45_savings),
            eb1_supply=int(total_eb1_supply),
            india_eb1_supply=int(india_eb1_supply),
        )

    def get_supply_breakdown(
        self,
        apply_freeze: bool = False,
        apply_real_restrictions: bool = False,
        policy_name: Optional[str] = None,
    ) -> SupplyBreakdown:
        """Compute the full waterfall-style supply breakdown.

        Accepts either:
        - policy_name: str — one of 'standard', 'freeze', 'real_restrictions'
        - apply_freeze / apply_real_restrictions: bool (legacy API, backward compat)

        apply_real_restrictions: Use ACTUAL_RESTRICTED_COUNTRIES from real 2025-2026
        Presidential Proclamations (distinct from hypothetical freeze).
        """
        self._ensure_dos_loaded()

        # Resolve policy from new or legacy API
        from ..domain.policies import FreezePolicy, RealRestrictionsPolicy

        if policy_name is not None and (apply_freeze or apply_real_restrictions):
            raise ValueError(
                "Cannot specify both policy_name and boolean flags "
                "(apply_freeze / apply_real_restrictions)"
            )

        if policy_name is not None:
            policy = self._resolve_policy(policy_name)
        elif apply_freeze:
            policy = FreezePolicy()
        elif apply_real_restrictions:
            policy = RealRestrictionsPolicy()
        else:
            policy = self._default_policy

        return self._compute_with_policy(policy)
