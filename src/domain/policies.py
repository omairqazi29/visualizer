"""Domain policy stubs for The Spillover Engine.

Stub implementations — class signatures and ``name`` attributes only.
Full logic will be migrated from src/engine/supply.py in PR3.

pandas is imported only under TYPE_CHECKING to keep the domain layer free of
heavyweight runtime dependencies.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pandas as pd

from .value_objects import PolicyName


class StandardPolicy:
    """Standard INA 201/203 spillover — no freeze, no restrictions."""

    name: PolicyName = PolicyName.STANDARD

    def compute_fb_savings(self, dos_df: pd.DataFrame) -> int:
        raise NotImplementedError("StandardPolicy.compute_fb_savings — stub, see PR3")

    def compute_eb45_savings(self, dos_df: pd.DataFrame) -> int:
        raise NotImplementedError("StandardPolicy.compute_eb45_savings — stub, see PR3")

    def adjust_india_eb1_supply(
        self,
        base_india_supply: int,
        fb_savings: int,
        eb45_savings: int,
        total_eb1_supply: int,
        dos_df: pd.DataFrame,
    ) -> int:
        raise NotImplementedError("StandardPolicy.adjust_india_eb1_supply — stub, see PR3")


class FreezePolicy:
    """Hypothetical 75-Country Freeze demand-curtailment scenario."""

    name: PolicyName = PolicyName.FREEZE

    def compute_fb_savings(self, dos_df: pd.DataFrame) -> int:
        raise NotImplementedError("FreezePolicy.compute_fb_savings — stub, see PR3")

    def compute_eb45_savings(self, dos_df: pd.DataFrame) -> int:
        raise NotImplementedError("FreezePolicy.compute_eb45_savings — stub, see PR3")

    def adjust_india_eb1_supply(
        self,
        base_india_supply: int,
        fb_savings: int,
        eb45_savings: int,
        total_eb1_supply: int,
        dos_df: pd.DataFrame,
    ) -> int:
        raise NotImplementedError("FreezePolicy.adjust_india_eb1_supply — stub, see PR3")


class RealRestrictionsPolicy:
    """Actual 2025-2026 Presidential Proclamation restrictions."""

    name: PolicyName = PolicyName.REAL_RESTRICTIONS

    def compute_fb_savings(self, dos_df: pd.DataFrame) -> int:
        raise NotImplementedError("RealRestrictionsPolicy.compute_fb_savings — stub, see PR3")

    def compute_eb45_savings(self, dos_df: pd.DataFrame) -> int:
        raise NotImplementedError("RealRestrictionsPolicy.compute_eb45_savings — stub, see PR3")

    def adjust_india_eb1_supply(
        self,
        base_india_supply: int,
        fb_savings: int,
        eb45_savings: int,
        total_eb1_supply: int,
        dos_df: pd.DataFrame,
    ) -> int:
        raise NotImplementedError("RealRestrictionsPolicy.adjust_india_eb1_supply — stub, see PR3")
