"""Tests for src/domain/ value objects, exceptions, protocols, and policy stubs."""

import pytest
from datetime import datetime

from src.domain.value_objects import (
    Chargeability,
    PolicyName,
    FiscalYear,
    INALimit,
    SupplyBreakdown,
    BacklogSnapshot,
    IndiaEB1Queue,
)
from src.domain.exceptions import (
    SpilloverError,
    DataLoadError,
    InvalidPolicyError,
    MathInvariantViolation,
)
from src.domain.protocols import SpilloverPolicy
from src.domain.policies import StandardPolicy, FreezePolicy, RealRestrictionsPolicy
from src.constants import (
    FB_STATUTORY_LIMIT,
    EB_BASE_LIMIT,
    EB1_STATUTORY_SHARE,
    PER_COUNTRY_CAP,
    DEPENDENT_MULTIPLIER,
)


# ---------------------------------------------------------------------------
# Value Objects
# ---------------------------------------------------------------------------


class TestPolicyName:
    def test_enum_values(self):
        assert PolicyName.STANDARD == "standard"
        assert PolicyName.FREEZE == "freeze"
        assert PolicyName.REAL_RESTRICTIONS == "real_restrictions"

    def test_enum_count(self):
        assert len(PolicyName) == 3

    def test_string_comparison(self):
        assert PolicyName.STANDARD == "standard"
        assert PolicyName("freeze") is PolicyName.FREEZE


class TestFiscalYear:
    def test_start_date(self):
        fy = FiscalYear(ending_year=2025)
        assert fy.start_date == datetime(2024, 10, 1)

    def test_end_date(self):
        fy = FiscalYear(ending_year=2025)
        assert fy.end_date == datetime(2025, 9, 30, 23, 59, 59)

    def test_str(self):
        assert str(FiscalYear(2026)) == "FY2026"

    def test_frozen(self):
        fy = FiscalYear(2025)
        with pytest.raises(AttributeError):
            fy.ending_year = 2026  # type: ignore[misc]

    def test_equality(self):
        assert FiscalYear(2025) == FiscalYear(2025)
        assert FiscalYear(2025) != FiscalYear(2026)


class TestINALimit:
    def test_defaults_match_constants(self):
        lim = INALimit()
        assert lim.fb_floor == FB_STATUTORY_LIMIT
        assert lim.eb_base == EB_BASE_LIMIT
        assert lim.eb1_share == EB1_STATUTORY_SHARE
        assert lim.per_country_cap == PER_COUNTRY_CAP
        assert lim.dependent_multiplier == DEPENDENT_MULTIPLIER

    def test_frozen(self):
        lim = INALimit()
        with pytest.raises(AttributeError):
            lim.fb_floor = 999999  # type: ignore[misc]

    def test_custom_values(self):
        lim = INALimit(fb_floor=300000, eb_base=200000)
        assert lim.fb_floor == 300000
        assert lim.eb_base == 200000


class TestSupplyBreakdown:
    def _make(self, **overrides):
        defaults = dict(
            eb_base_limit=140000,
            fb_spillover_std=10000,
            fb_savings_freeze=0,
            eb45_spillover_std=5000,
            eb45_savings_freeze=0,
            total_eb_supply=155000,
            eb1_supply=44330,
            india_eb1_supply=6952,
        )
        defaults.update(overrides)
        return SupplyBreakdown(**defaults)

    def test_construction(self):
        sb = self._make()
        assert sb.india_eb1_supply == 6952
        assert sb.policy_applied == PolicyName.STANDARD

    def test_negative_india_supply_raises(self):
        with pytest.raises(ValueError, match="india_eb1_supply cannot be negative"):
            self._make(india_eb1_supply=-1)

    def test_zero_india_supply_ok(self):
        sb = self._make(india_eb1_supply=0)
        assert sb.india_eb1_supply == 0

    def test_computed_at_auto(self):
        sb = self._make()
        assert isinstance(sb.computed_at, datetime)

    def test_policy_applied_override(self):
        sb = self._make(policy_applied=PolicyName.FREEZE)
        assert sb.policy_applied == PolicyName.FREEZE

    def test_source_data_checksum(self):
        sb = self._make(source_data_checksum="abc123")
        assert sb.source_data_checksum == "abc123"


class TestBacklogSnapshot:
    def test_construction(self):
        snap = BacklogSnapshot(mountain=39127, valley=9035, total=48162)
        assert snap.mountain == 39127
        assert snap.total == 48162

    def test_negative_total_raises(self):
        with pytest.raises(ValueError, match="total cannot be negative"):
            BacklogSnapshot(mountain=0, valley=0, total=-1)

    def test_frozen(self):
        snap = BacklogSnapshot(mountain=100, valley=50, total=150)
        with pytest.raises(AttributeError):
            snap.mountain = 200  # type: ignore[misc]

    def test_as_of(self):
        dt = datetime(2026, 1, 15)
        snap = BacklogSnapshot(mountain=100, valley=50, total=150, as_of=dt)
        assert snap.as_of == dt


class TestIndiaEB1Queue:
    def test_construction(self):
        q = IndiaEB1Queue(mountain=39127, valley=9035, total=60000)
        assert q.mountain == 39127

    def test_pipeline_excess(self):
        q = IndiaEB1Queue(mountain=39127, valley=9035, total=60000)
        assert q.pipeline_excess == 60000 - 39127 - 9035

    def test_pipeline_excess_no_pipeline(self):
        q = IndiaEB1Queue(mountain=100, valley=50, total=150)
        assert q.pipeline_excess == 0


class TestChargeability:
    def test_newtype(self):
        c = Chargeability("India")
        assert c == "India"
        assert isinstance(c, str)


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class TestExceptionHierarchy:
    def test_base_exception(self):
        assert issubclass(SpilloverError, Exception)

    def test_data_load_error(self):
        assert issubclass(DataLoadError, SpilloverError)

    def test_invalid_policy_error(self):
        assert issubclass(InvalidPolicyError, SpilloverError)

    def test_math_invariant_violation(self):
        assert issubclass(MathInvariantViolation, SpilloverError)

    def test_catch_base(self):
        with pytest.raises(SpilloverError):
            raise DataLoadError("test")

    def test_message(self):
        err = MathInvariantViolation("supply went negative")
        assert "supply went negative" in str(err)


# ---------------------------------------------------------------------------
# Protocols & Policy Stubs
# ---------------------------------------------------------------------------


class TestPolicyStubs:
    def test_standard_policy_name(self):
        p = StandardPolicy()
        assert p.name == PolicyName.STANDARD

    def test_freeze_policy_name(self):
        p = FreezePolicy()
        assert p.name == PolicyName.FREEZE

    def test_real_restrictions_policy_name(self):
        p = RealRestrictionsPolicy()
        assert p.name == PolicyName.REAL_RESTRICTIONS

    def test_standard_stubs_raise(self):
        import pandas as pd

        p = StandardPolicy()
        df = pd.DataFrame()
        with pytest.raises(NotImplementedError):
            p.compute_fb_savings(df)
        with pytest.raises(NotImplementedError):
            p.compute_eb45_savings(df)
        with pytest.raises(NotImplementedError):
            p.adjust_india_eb1_supply(0, 0, 0, 0, df)

    def test_spillover_policy_protocol_check(self):
        """Policy stubs should satisfy the SpilloverPolicy protocol at runtime."""
        assert isinstance(StandardPolicy(), SpilloverPolicy)
        assert isinstance(FreezePolicy(), SpilloverPolicy)
        assert isinstance(RealRestrictionsPolicy(), SpilloverPolicy)
