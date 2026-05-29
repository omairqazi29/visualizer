"""Tests for SpilloverPolicy implementations and pure helper functions.

Covers StandardPolicy, FreezePolicy, RealRestrictionsPolicy (src/domain/policies.py)
and the extracted pure helpers apply_freeze_to_df / calculate_savings_from_freeze
(src/engine/redistribution.py).
"""

import pytest
import pandas as pd

from src.domain.protocols import SpilloverPolicy
from src.domain.policies import StandardPolicy, FreezePolicy, RealRestrictionsPolicy
from src.domain.value_objects import PolicyName
from src.engine.redistribution import apply_freeze_to_df, calculate_savings_from_freeze
from src.constants import (
    DEFAULT_RESTRICTED_COUNTRIES,
    ACTUAL_RESTRICTED_COUNTRIES,
    FB_CATEGORIES,
    EB45_CATEGORIES,
    EB1_STATUTORY_SHARE,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def dos_df_with_actual_restricted() -> pd.DataFrame:
    """Synthetic DOS DataFrame containing actual restricted countries.

    Ensures RealRestrictionsPolicy produces non-zero savings.
    """
    data = [
        # FB categories — some from ACTUAL_RESTRICTED_COUNTRIES
        {"chargeability": "Haiti", "visa_category": "F1", "count": 4000, "report_month": 1, "report_year": 2025},
        {"chargeability": "Nigeria", "visa_category": "F2A", "count": 6000, "report_month": 2, "report_year": 2025},
        {"chargeability": "India", "visa_category": "F3", "count": 5000, "report_month": 3, "report_year": 2025},
        # EB-1 categories
        {"chargeability": "India", "visa_category": "E11", "count": 3000, "report_month": 1, "report_year": 2025},
        {"chargeability": "United Kingdom", "visa_category": "E11", "count": 800, "report_month": 2, "report_year": 2025},
        # EB-4/5 categories — some from ACTUAL_RESTRICTED_COUNTRIES
        {"chargeability": "Venezuela", "visa_category": "SD", "count": 700, "report_month": 1, "report_year": 2025},
        {"chargeability": "Cuba", "visa_category": "SE", "count": 300, "report_month": 2, "report_year": 2025},
        {"chargeability": "India", "visa_category": "C5", "count": 200, "report_month": 3, "report_year": 2025},
    ]
    return pd.DataFrame(data)


# ---------------------------------------------------------------------------
# Pure helper functions
# ---------------------------------------------------------------------------


class TestApplyFreezeToDf:
    def test_zeros_restricted_countries(self):
        df = pd.DataFrame({
            'chargeability': ['India', 'Mexico', 'Philippines'],
            'count': [100, 200, 300],
        })
        frozen = apply_freeze_to_df(df, {'Mexico', 'Philippines'})
        assert frozen.loc[0, 'count'] == 100  # India unchanged
        assert frozen.loc[1, 'count'] == 0    # Mexico zeroed
        assert frozen.loc[2, 'count'] == 0    # Philippines zeroed

    def test_case_insensitive(self):
        df = pd.DataFrame({
            'chargeability': ['mexico', 'MEXICO', 'Mexico'],
            'count': [100, 200, 300],
        })
        frozen = apply_freeze_to_df(df, {'Mexico'})
        assert frozen['count'].sum() == 0

    def test_no_mutation_of_original(self):
        df = pd.DataFrame({'chargeability': ['Mexico'], 'count': [500]})
        _ = apply_freeze_to_df(df, {'Mexico'})
        assert df.loc[0, 'count'] == 500  # original unchanged

    def test_empty_restricted_set(self):
        df = pd.DataFrame({'chargeability': ['India'], 'count': [100]})
        frozen = apply_freeze_to_df(df, set())
        assert frozen.loc[0, 'count'] == 100

    def test_empty_dataframe(self):
        df = pd.DataFrame({'chargeability': [], 'count': []})
        frozen = apply_freeze_to_df(df, {'Mexico'})
        assert len(frozen) == 0


class TestCalculateSavingsFromFreeze:
    def test_basic_savings(self):
        original = pd.DataFrame({'count': [100, 200, 300]})
        frozen = pd.DataFrame({'count': [100, 0, 0]})
        assert calculate_savings_from_freeze(original, frozen) == 500

    def test_no_savings(self):
        df = pd.DataFrame({'count': [100, 200]})
        assert calculate_savings_from_freeze(df, df.copy()) == 0

    def test_all_frozen(self):
        original = pd.DataFrame({'count': [100, 200]})
        frozen = pd.DataFrame({'count': [0, 0]})
        assert calculate_savings_from_freeze(original, frozen) == 300


# ---------------------------------------------------------------------------
# Protocol compliance
# ---------------------------------------------------------------------------


class TestProtocolCompliance:
    def test_standard_satisfies_protocol(self):
        assert isinstance(StandardPolicy(), SpilloverPolicy)

    def test_freeze_satisfies_protocol(self):
        assert isinstance(FreezePolicy(), SpilloverPolicy)

    def test_real_restrictions_satisfies_protocol(self):
        assert isinstance(RealRestrictionsPolicy(), SpilloverPolicy)


# ---------------------------------------------------------------------------
# StandardPolicy
# ---------------------------------------------------------------------------


class TestStandardPolicy:
    def test_name(self):
        assert StandardPolicy().name == PolicyName.STANDARD

    def test_fb_savings_zero(self, sample_dos_df):
        assert StandardPolicy().compute_fb_savings(sample_dos_df) == 0

    def test_eb45_savings_zero(self, sample_dos_df):
        assert StandardPolicy().compute_eb45_savings(sample_dos_df) == 0

    def test_adjust_returns_base_unchanged(self, sample_dos_df):
        p = StandardPolicy()
        result = p.adjust_india_eb1_supply(
            base_india_supply=6952,
            fb_savings=0,
            eb45_savings=0,
            total_eb1_supply=50000,
            dos_df=sample_dos_df,
        )
        assert result == 6952

    def test_adjust_ignores_savings_args(self, sample_dos_df):
        """Even if savings are passed, StandardPolicy returns base unchanged."""
        p = StandardPolicy()
        result = p.adjust_india_eb1_supply(
            base_india_supply=6952,
            fb_savings=9999,
            eb45_savings=9999,
            total_eb1_supply=99999,
            dos_df=sample_dos_df,
        )
        assert result == 6952

    def test_empty_df(self):
        p = StandardPolicy()
        df = pd.DataFrame(columns=['chargeability', 'visa_category', 'count'])
        assert p.compute_fb_savings(df) == 0
        assert p.compute_eb45_savings(df) == 0
        assert p.adjust_india_eb1_supply(100, 0, 0, 0, df) == 100


# ---------------------------------------------------------------------------
# FreezePolicy
# ---------------------------------------------------------------------------


class TestFreezePolicy:
    def test_name(self):
        assert FreezePolicy().name == PolicyName.FREEZE

    def test_fb_savings(self, sample_dos_df):
        """FB savings = sum of FB counts for restricted countries.

        From conftest sample_dos_df:
        Mexico(F1, 20000) + Philippines(F2A, 15000) + Dominican Republic(F2B, 10000)
        + China-mainland(F4, 8000) + Vietnam(FX, 3000) = 56000.
        India(F3, 5000) is NOT restricted.
        """
        p = FreezePolicy()
        savings = p.compute_fb_savings(sample_dos_df)
        assert savings == 56000

    def test_eb45_savings(self, sample_dos_df):
        """EB-4/5 savings = sum of EB45 counts for restricted countries.

        From conftest sample_dos_df:
        China-mainland(I5, 1000) is restricted. Others (El Salvador, Guatemala, India) are not.
        """
        p = FreezePolicy()
        savings = p.compute_eb45_savings(sample_dos_df)
        assert savings == 1000

    def test_adjust_india_eb1_supply(self, sample_dos_df):
        """Under freeze, India EB-1 = total_eb1_supply - non_India_EB1_usage.

        Non-India EB-1 usage: China-mainland(E13, 1500) + UK(E11, 800) = 2300.
        """
        p = FreezePolicy()
        result = p.adjust_india_eb1_supply(
            base_india_supply=6952,
            fb_savings=56000,
            eb45_savings=1000,
            total_eb1_supply=50000,
            dos_df=sample_dos_df,
        )
        assert result == 50000 - 2300  # 47700

    def test_adjust_floors_at_zero(self, sample_dos_df):
        """If total_eb1_supply < non-India usage, result is floored at 0."""
        p = FreezePolicy()
        result = p.adjust_india_eb1_supply(
            base_india_supply=6952,
            fb_savings=0,
            eb45_savings=0,
            total_eb1_supply=1000,  # less than non-India usage (2300)
            dos_df=sample_dos_df,
        )
        assert result == 0

    def test_uses_default_restricted_countries(self, sample_dos_df):
        """FreezePolicy must use DEFAULT_RESTRICTED_COUNTRIES, not ACTUAL."""
        p = FreezePolicy()
        # Manually compute expected FB savings using DEFAULT_RESTRICTED_COUNTRIES
        fb_df = sample_dos_df[sample_dos_df['visa_category'].isin(FB_CATEGORIES)]
        restricted_lower = {c.lower() for c in DEFAULT_RESTRICTED_COUNTRIES}
        expected = fb_df[fb_df['chargeability'].str.lower().isin(restricted_lower)]['count'].sum()
        assert p.compute_fb_savings(sample_dos_df) == expected

    def test_empty_df(self):
        p = FreezePolicy()
        df = pd.DataFrame(columns=['chargeability', 'visa_category', 'count'])
        assert p.compute_fb_savings(df) == 0
        assert p.compute_eb45_savings(df) == 0


# ---------------------------------------------------------------------------
# RealRestrictionsPolicy
# ---------------------------------------------------------------------------


class TestRealRestrictionsPolicy:
    def test_name(self):
        assert RealRestrictionsPolicy().name == PolicyName.REAL_RESTRICTIONS

    def test_fb_savings_with_actual_countries(self, dos_df_with_actual_restricted):
        """FB savings from actual restricted countries.

        Haiti(F1, 4000) + Nigeria(F2A, 6000) = 10000.
        India(F3, 5000) is NOT restricted.
        """
        p = RealRestrictionsPolicy()
        savings = p.compute_fb_savings(dos_df_with_actual_restricted)
        assert savings == 10000

    def test_eb45_savings_with_actual_countries(self, dos_df_with_actual_restricted):
        """EB-4/5 savings from actual restricted countries.

        Venezuela(SD, 700) + Cuba(SE, 300) = 1000.
        India(C5, 200) is NOT restricted.
        """
        p = RealRestrictionsPolicy()
        savings = p.compute_eb45_savings(dos_df_with_actual_restricted)
        assert savings == 1000

    def test_no_savings_when_no_restricted_present(self, sample_dos_df):
        """sample_dos_df has no ACTUAL_RESTRICTED_COUNTRIES → zero savings."""
        p = RealRestrictionsPolicy()
        assert p.compute_fb_savings(sample_dos_df) == 0
        assert p.compute_eb45_savings(sample_dos_df) == 0

    def test_adjust_adds_savings_to_base(self):
        """Real restrictions add savings to base India supply."""
        p = RealRestrictionsPolicy()
        df = pd.DataFrame(columns=['chargeability', 'visa_category', 'count'])
        result = p.adjust_india_eb1_supply(
            base_india_supply=6952,
            fb_savings=1000,
            eb45_savings=500,
            total_eb1_supply=50000,
            dos_df=df,
        )
        # 6952 + 500 + int(1000 * 0.286) = 6952 + 500 + 286 = 7738
        assert result == 6952 + 500 + int(1000 * EB1_STATUTORY_SHARE)

    def test_adjust_zero_savings(self):
        """With zero savings, returns base unchanged."""
        p = RealRestrictionsPolicy()
        df = pd.DataFrame(columns=['chargeability', 'visa_category', 'count'])
        result = p.adjust_india_eb1_supply(
            base_india_supply=6952,
            fb_savings=0,
            eb45_savings=0,
            total_eb1_supply=50000,
            dos_df=df,
        )
        assert result == 6952

    def test_uses_actual_restricted_countries(self, dos_df_with_actual_restricted):
        """RealRestrictionsPolicy must use ACTUAL_RESTRICTED_COUNTRIES, not DEFAULT."""
        p = RealRestrictionsPolicy()
        # Manually compute expected EB45 savings using ACTUAL_RESTRICTED_COUNTRIES
        eb45_df = dos_df_with_actual_restricted[
            dos_df_with_actual_restricted['visa_category'].isin(EB45_CATEGORIES)
        ]
        restricted_lower = {c.lower() for c in ACTUAL_RESTRICTED_COUNTRIES}
        expected = eb45_df[eb45_df['chargeability'].str.lower().isin(restricted_lower)]['count'].sum()
        assert p.compute_eb45_savings(dos_df_with_actual_restricted) == expected

    def test_empty_df(self):
        p = RealRestrictionsPolicy()
        df = pd.DataFrame(columns=['chargeability', 'visa_category', 'count'])
        assert p.compute_fb_savings(df) == 0
        assert p.compute_eb45_savings(df) == 0


# ---------------------------------------------------------------------------
# Cross-policy comparisons
# ---------------------------------------------------------------------------


class TestPolicyCrossComparisons:
    def test_freeze_savings_ge_real_on_sample(self, sample_dos_df):
        """On sample_dos_df, freeze savings >= real restrictions savings."""
        freeze = FreezePolicy()
        real = RealRestrictionsPolicy()
        assert freeze.compute_fb_savings(sample_dos_df) >= real.compute_fb_savings(sample_dos_df)
        assert freeze.compute_eb45_savings(sample_dos_df) >= real.compute_eb45_savings(sample_dos_df)

    def test_standard_always_zero(self, sample_dos_df):
        """Standard savings are always zero regardless of data."""
        std = StandardPolicy()
        assert std.compute_fb_savings(sample_dos_df) == 0
        assert std.compute_eb45_savings(sample_dos_df) == 0

    def test_all_policies_share_protocol(self):
        """All three policies satisfy SpilloverPolicy."""
        for cls in (StandardPolicy, FreezePolicy, RealRestrictionsPolicy):
            assert isinstance(cls(), SpilloverPolicy)
