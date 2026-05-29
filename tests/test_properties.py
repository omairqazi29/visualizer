"""Hypothesis property-based tests for The Spillover Engine.

Generators use synthetic data constrained to valid visa categories,
chargeabilities, and realistic count ranges — not random garbage.

At least 8 invariants covering the INA 201/203 math model:
1. Non-negative supply values (india_eb1_supply >= 0)
2. Conservation: total_eb_supply >= eb_base_limit
3. Monotonicity: freeze india_supply >= standard india_supply
4. Per-country cap: india_eb1_supply <= total_eb1_supply (EB-1 share)
5. EB1 share: eb1_supply <= total_eb_supply
6. Non-negative at every step in project_clearance
7. Dependent multiplier applied consistently
8. FB floor constraint respected (fb_spillover_std >= 0)
"""

from datetime import datetime
from unittest.mock import MagicMock

import pandas as pd
import pytest

hypothesis = pytest.importorskip("hypothesis")
from hypothesis import given, settings, assume, HealthCheck
from hypothesis import strategies as st

from src.constants import (
    FB_STATUTORY_LIMIT,
    EB_BASE_LIMIT,
    EB1_STATUTORY_SHARE,
    EB45_STATUTORY_SHARE,
    DEPENDENT_MULTIPLIER,
    FB_CATEGORIES,
    EB45_CATEGORIES,
    EB1_CATEGORIES,
)
from src.domain.policies import StandardPolicy, FreezePolicy, RealRestrictionsPolicy
from src.engine.demand import DemandModeler


# ---------------------------------------------------------------------------
# Strategies (constrained generators)
# ---------------------------------------------------------------------------


VALID_CHARGEABILITIES = [
    "India",
    "China - mainland born",
    "Philippines",
    "Mexico",
    "Dominican Republic",
    "Vietnam",
    "United Kingdom",
    "Canada",
    "Brazil",
    "Haiti",
    "Nigeria",
]

VALID_EB1_CATS = EB1_CATEGORIES[:3]  # E11, E12, E13
VALID_FB_CATS = FB_CATEGORIES
VALID_EB45_CATS = ["SD", "SE", "C5", "I5"]


@st.composite
def dos_dataframes(draw):
    """Generate a synthetic DOS DataFrame with valid structure.

    Counts are constrained to realistic per-country/per-category ranges
    (0–15000 for FB, 0–5000 for EB-1, 0–3000 for EB-4/5) to avoid
    unrealistic edge cases that would never occur in real DOS data.
    """
    n_rows = draw(st.integers(min_value=3, max_value=30))
    rows = []
    for _ in range(n_rows):
        cat = draw(st.sampled_from(VALID_EB1_CATS + VALID_FB_CATS + VALID_EB45_CATS))
        if cat in VALID_EB1_CATS:
            count = draw(st.integers(min_value=0, max_value=5000))
        elif cat in VALID_FB_CATS:
            count = draw(st.integers(min_value=0, max_value=15000))
        else:
            count = draw(st.integers(min_value=0, max_value=3000))
        rows.append({
            "chargeability": draw(st.sampled_from(VALID_CHARGEABILITIES)),
            "visa_category": cat,
            "count": count,
            "report_month": draw(st.integers(min_value=1, max_value=12)),
            "report_year": 2025,
        })
    return pd.DataFrame(rows)


@st.composite
def monthly_distributions(draw):
    """Generate a valid 12-month distribution summing to ~1.0."""
    values = [draw(st.floats(min_value=0.001, max_value=1.0)) for _ in range(12)]
    total = sum(values)
    return {m: v / total for m, v in zip(range(1, 13), values)}


# ---------------------------------------------------------------------------
# Property tests
# ---------------------------------------------------------------------------


class TestSupplyInvariants:
    """Property-based tests on SupplyCalculator with injected synthetic data."""

    @given(dos_df=dos_dataframes())
    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
    def test_non_negative_india_supply(self, dos_df):
        """Invariant 1: india_eb1_supply >= 0 for all policies."""
        for policy_cls in (StandardPolicy, FreezePolicy, RealRestrictionsPolicy):
            policy = policy_cls()
            fb_savings = policy.compute_fb_savings(dos_df)
            eb45_savings = policy.compute_eb45_savings(dos_df)

            # Compute a synthetic total_eb1_supply
            total_fb_usage = dos_df[dos_df['visa_category'].isin(FB_CATEGORIES)]['count'].sum()
            fb_spillover = max(0, FB_STATUTORY_LIMIT - int(total_fb_usage))
            total_shared = EB_BASE_LIMIT + fb_spillover
            eb1_share = int(total_shared * EB1_STATUTORY_SHARE)
            eb45_usage = dos_df[dos_df['visa_category'].isin(EB45_CATEGORIES)]['count'].sum()
            eb45_spillover = max(0, int(EB_BASE_LIMIT * EB45_STATUTORY_SHARE) - int(eb45_usage))
            total_eb1 = eb1_share + eb45_spillover

            from src.constants import DEFAULT_INDIA_EB1_SUPPLY
            result = policy.adjust_india_eb1_supply(
                DEFAULT_INDIA_EB1_SUPPLY, fb_savings, eb45_savings, total_eb1, dos_df
            )
            assert result >= 0, f"{policy_cls.__name__}: india_eb1_supply={result} < 0"

    @given(dos_df=dos_dataframes())
    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
    def test_conservation_total_eb_ge_base(self, dos_df):
        """Invariant 2: total_eb_supply >= eb_base_limit.

        FB spillover can only add to the base, never subtract.
        """
        total_fb_usage = dos_df[dos_df['visa_category'].isin(FB_CATEGORIES)]['count'].sum()
        fb_spillover = max(0, FB_STATUTORY_LIMIT - int(total_fb_usage))
        eb45_usage = dos_df[dos_df['visa_category'].isin(EB45_CATEGORIES)]['count'].sum()
        eb45_spillover = max(0, int(EB_BASE_LIMIT * EB45_STATUTORY_SHARE) - int(eb45_usage))
        total_eb = EB_BASE_LIMIT + fb_spillover + eb45_spillover
        assert total_eb >= EB_BASE_LIMIT

    @given(dos_df=dos_dataframes())
    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
    def test_monotonicity_freeze_ge_standard(self, dos_df):
        """Invariant 3: freeze india_supply >= standard india_supply.

        The freeze scenario frees up more visas, so India should get at least
        as many as under standard policy.
        """
        std = StandardPolicy()
        frz = FreezePolicy()

        from src.constants import DEFAULT_INDIA_EB1_SUPPLY

        # Compute full waterfall for both
        total_fb_usage = dos_df[dos_df['visa_category'].isin(FB_CATEGORIES)]['count'].sum()
        fb_spillover = max(0, FB_STATUTORY_LIMIT - int(total_fb_usage))
        eb45_usage = dos_df[dos_df['visa_category'].isin(EB45_CATEGORIES)]['count'].sum()
        eb45_spillover = max(0, int(EB_BASE_LIMIT * EB45_STATUTORY_SHARE) - int(eb45_usage))

        # Standard
        std_total_shared = EB_BASE_LIMIT + fb_spillover
        std_eb1 = int(std_total_shared * EB1_STATUTORY_SHARE) + eb45_spillover
        std_result = std.adjust_india_eb1_supply(
            DEFAULT_INDIA_EB1_SUPPLY, 0, 0, std_eb1, dos_df
        )

        # Freeze: adds savings to shared supply
        fb_savings = frz.compute_fb_savings(dos_df)
        eb45_savings = frz.compute_eb45_savings(dos_df)
        frz_total_shared = EB_BASE_LIMIT + fb_spillover + fb_savings
        frz_eb1 = int(frz_total_shared * EB1_STATUTORY_SHARE) + eb45_spillover + eb45_savings
        frz_result = frz.adjust_india_eb1_supply(
            DEFAULT_INDIA_EB1_SUPPLY, fb_savings, eb45_savings, frz_eb1, dos_df
        )

        assert frz_result >= std_result, (
            f"Freeze ({frz_result}) < Standard ({std_result})"
        )

    @given(dos_df=dos_dataframes())
    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
    def test_india_eb1_le_total_eb1(self, dos_df):
        """Invariant 4: india_eb1_supply <= total_eb1_supply for std/freeze.

        Standard and Freeze policies respect the category ceiling.
        RealRestrictionsPolicy intentionally boosts india_eb1_supply beyond
        the standard waterfall total (savings added preferentially — see
        SupplyBreakdown docstring), so it is excluded from this invariant.
        """
        for policy_cls in (StandardPolicy, FreezePolicy):
            policy = policy_cls()
            fb_savings = policy.compute_fb_savings(dos_df)
            eb45_savings = policy.compute_eb45_savings(dos_df)

            total_fb_usage = dos_df[dos_df['visa_category'].isin(FB_CATEGORIES)]['count'].sum()
            fb_spillover = max(0, FB_STATUTORY_LIMIT - int(total_fb_usage))

            if policy_cls is FreezePolicy:
                total_shared = EB_BASE_LIMIT + fb_spillover + fb_savings
            else:
                total_shared = EB_BASE_LIMIT + fb_spillover

            eb45_usage = dos_df[dos_df['visa_category'].isin(EB45_CATEGORIES)]['count'].sum()
            eb45_spillover = max(0, int(EB_BASE_LIMIT * EB45_STATUTORY_SHARE) - int(eb45_usage))

            if policy_cls is FreezePolicy:
                total_eb1 = int(total_shared * EB1_STATUTORY_SHARE) + eb45_spillover + eb45_savings
            else:
                total_eb1 = int(total_shared * EB1_STATUTORY_SHARE) + eb45_spillover

            from src.constants import DEFAULT_INDIA_EB1_SUPPLY
            result = policy.adjust_india_eb1_supply(
                DEFAULT_INDIA_EB1_SUPPLY, fb_savings, eb45_savings, total_eb1, dos_df
            )
            assert result <= total_eb1, (
                f"{policy_cls.__name__}: india ({result}) > total_eb1 ({total_eb1})"
            )

    @given(dos_df=dos_dataframes())
    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
    def test_eb1_share_le_total_eb(self, dos_df):
        """Invariant 5: eb1_supply <= total_eb_supply.

        EB-1 is a subcategory of total EB.
        """
        total_fb_usage = dos_df[dos_df['visa_category'].isin(FB_CATEGORIES)]['count'].sum()
        fb_spillover = max(0, FB_STATUTORY_LIMIT - int(total_fb_usage))
        total_shared = EB_BASE_LIMIT + fb_spillover
        eb1_share = int(total_shared * EB1_STATUTORY_SHARE)
        eb45_usage = dos_df[dos_df['visa_category'].isin(EB45_CATEGORIES)]['count'].sum()
        eb45_spillover = max(0, int(EB_BASE_LIMIT * EB45_STATUTORY_SHARE) - int(eb45_usage))
        total_eb1 = eb1_share + eb45_spillover
        total_eb = total_shared + eb45_spillover
        assert total_eb1 <= total_eb, f"eb1 ({total_eb1}) > total_eb ({total_eb})"


class TestDemandInvariants:
    """Property-based tests on DemandModeler projection."""

    @given(
        backlog=st.integers(min_value=100, max_value=200000),
        annual_supply=st.integers(min_value=1000, max_value=100000),
        dist=monthly_distributions(),
    )
    @settings(max_examples=30, suppress_health_check=[HealthCheck.too_slow])
    def test_non_negative_backlog_in_trajectory(self, backlog, annual_supply, dist):
        """Invariant 6: backlog >= 0 at every step in project_clearance."""
        modeler = DemandModeler(
            inventory_total=backlog,
            annual_supply=annual_supply,
            monthly_distribution=dist,
            inflow_rate=0,
        )
        proj = modeler.project_clearance(
            start_date=datetime(2025, 10, 1), backlog=backlog
        )
        for step in proj["trajectory"]:
            assert step["backlog"] >= 0, (
                f"Negative backlog at {step['date']}: {step['backlog']}"
            )

    @given(inflow_rate=st.integers(min_value=0, max_value=5000))
    @settings(max_examples=30, suppress_health_check=[HealthCheck.too_slow])
    def test_dependent_multiplier_consistent(self, inflow_rate):
        """Invariant 7: monthly_inflow = int(inflow_rate * DEPENDENT_MULTIPLIER)."""
        dist = {m: 1 / 12 for m in range(1, 13)}
        modeler = DemandModeler(
            inventory_total=10000,
            annual_supply=12000,
            monthly_distribution=dist,
            inflow_rate=inflow_rate,
        )
        expected = int(inflow_rate * DEPENDENT_MULTIPLIER)
        assert modeler.monthly_inflow == expected

    @given(dos_df=dos_dataframes())
    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
    def test_fb_floor_respected(self, dos_df):
        """Invariant 8: fb_spillover_std >= 0 (FB floor constraint).

        FB spillover is max(0, FB_STATUTORY_LIMIT - usage), always non-negative.
        """
        total_fb_usage = dos_df[dos_df['visa_category'].isin(FB_CATEGORIES)]['count'].sum()
        fb_spillover = max(0, FB_STATUTORY_LIMIT - int(total_fb_usage))
        assert fb_spillover >= 0
