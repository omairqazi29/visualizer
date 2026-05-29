"""Tests for SupplyCalculator DI refactoring, shadow verification, and backward compat.

Covers:
- DI constructor with mock loader and policy
- Backward compatibility (old boolean flag interface, dos_parser property)
- Shadow dual-run fidelity verification
- New policy_name API
"""

import pytest
from unittest.mock import MagicMock

from src.engine.supply import SupplyCalculator, SupplyBreakdown
from src.domain.policies import StandardPolicy, FreezePolicy, RealRestrictionsPolicy
from src.domain.protocols import DOSDataLoader
from src.adapters.pandas_dos_loader import PandasDOSLoader
from src.constants import DEFAULT_INDIA_EB1_SUPPLY


# ---------------------------------------------------------------------------
# DI Constructor
# ---------------------------------------------------------------------------


class TestDIConstructor:
    """Test dependency injection constructor."""

    def test_default_constructor(self):
        """Default constructor creates StandardPolicy and PandasDOSLoader."""
        calc = SupplyCalculator()
        assert isinstance(calc._default_policy, StandardPolicy)
        assert isinstance(calc._loader, PandasDOSLoader)

    def test_custom_loader(self, sample_dos_df):
        """Custom loader is invoked when dos_parser is accessed."""
        mock_loader = MagicMock()
        mock_loader.load_all_issuances.return_value = sample_dos_df

        calc = SupplyCalculator(dos_loader=mock_loader)
        _ = calc.dos_parser
        mock_loader.load_all_issuances.assert_called_once()

    def test_custom_policy(self):
        """Custom default policy is stored."""
        policy = FreezePolicy()
        calc = SupplyCalculator(policy=policy)
        assert calc._default_policy is policy

    def test_custom_redistribution(self):
        """Custom redistribution engine is stored."""
        from src.engine.redistribution import RedistributionEngine
        engine = RedistributionEngine({"TestCountry"})
        calc = SupplyCalculator(redistribution=engine)
        assert calc._redistribution is engine

    def test_dos_dir_backward_compat(self):
        """dos_dir parameter still works as a public attribute."""
        calc = SupplyCalculator(dos_dir="custom/path")
        assert calc.dos_dir == "custom/path"

    def test_pandas_dos_loader_satisfies_protocol(self):
        """PandasDOSLoader satisfies DOSDataLoader protocol."""
        loader = PandasDOSLoader()
        assert isinstance(loader, DOSDataLoader)


# ---------------------------------------------------------------------------
# Backward Compatibility
# ---------------------------------------------------------------------------


class TestBackwardCompat:
    """Test that old API surface still works unchanged."""

    def test_boolean_flag_standard(self):
        """Default call (no flags) returns standard breakdown."""
        calc = SupplyCalculator()
        result = calc.get_supply_breakdown(apply_freeze=False, apply_real_restrictions=False)
        assert isinstance(result, SupplyBreakdown)
        assert result.india_eb1_supply == DEFAULT_INDIA_EB1_SUPPLY

    def test_boolean_flag_freeze(self):
        """apply_freeze=True produces non-zero freeze savings."""
        calc = SupplyCalculator()
        result = calc.get_supply_breakdown(apply_freeze=True)
        assert isinstance(result, SupplyBreakdown)
        assert result.fb_savings_freeze > 0

    def test_boolean_flag_real_restrictions(self):
        """apply_real_restrictions=True boosts India EB-1 supply."""
        calc = SupplyCalculator()
        result = calc.get_supply_breakdown(apply_real_restrictions=True)
        assert isinstance(result, SupplyBreakdown)
        assert result.india_eb1_supply > DEFAULT_INDIA_EB1_SUPPLY

    def test_freeze_precedence_over_real(self):
        """When both flags are True, freeze takes precedence (real savings stay 0)."""
        calc = SupplyCalculator()
        freeze_only = calc.get_supply_breakdown(apply_freeze=True, apply_real_restrictions=False)
        both = calc.get_supply_breakdown(apply_freeze=True, apply_real_restrictions=True)
        assert both.fb_savings_freeze == freeze_only.fb_savings_freeze
        assert both.india_eb1_supply == freeze_only.india_eb1_supply

    def test_dos_parser_property_returns_parser(self):
        """dos_parser property returns a usable DOSParser with data."""
        calc = SupplyCalculator()
        parser = calc.dos_parser
        assert parser is not None
        assert parser.df is not None
        assert len(parser.df) > 0

    def test_dos_parser_get_monthly_distribution(self):
        """dos_parser.get_monthly_distribution() works (used by api/main.py)."""
        calc = SupplyCalculator()
        dist = calc.dos_parser.get_monthly_distribution(
            country="India", categories=["E11", "E12", "E13"]
        )
        assert isinstance(dist, dict)
        assert len(dist) == 12


# ---------------------------------------------------------------------------
# Shadow Dual-Run Verification
# ---------------------------------------------------------------------------


class TestShadowVerification:
    """Test internal shadow dual-run catches drift."""

    def test_shadow_passes_standard(self):
        """Shadow verification passes for standard (no flags) — paths agree."""
        calc = SupplyCalculator()
        result = calc.get_supply_breakdown()
        assert isinstance(result, SupplyBreakdown)

    def test_shadow_passes_freeze(self):
        """Shadow verification passes for freeze scenario — paths agree."""
        calc = SupplyCalculator()
        result = calc.get_supply_breakdown(apply_freeze=True)
        assert isinstance(result, SupplyBreakdown)

    def test_shadow_passes_real_restrictions(self):
        """Shadow verification passes for real restrictions — paths agree."""
        calc = SupplyCalculator()
        result = calc.get_supply_breakdown(apply_real_restrictions=True)
        assert isinstance(result, SupplyBreakdown)

    def test_shadow_catches_drift(self, monkeypatch):
        """Shadow verification raises AssertionError when new path drifts."""
        calc = SupplyCalculator()
        original_compute = calc._compute_with_policy

        def drifted_compute(policy):
            result = original_compute(policy)
            # Return a result with intentionally drifted india_eb1_supply
            return SupplyBreakdown(
                eb_base_limit=result.eb_base_limit,
                fb_spillover_std=result.fb_spillover_std,
                fb_savings_freeze=result.fb_savings_freeze,
                eb45_spillover_std=result.eb45_spillover_std,
                eb45_savings_freeze=result.eb45_savings_freeze,
                total_eb_supply=result.total_eb_supply,
                eb1_supply=result.eb1_supply,
                india_eb1_supply=result.india_eb1_supply + 100,
            )

        monkeypatch.setattr(calc, '_compute_with_policy', drifted_compute)

        with pytest.raises(AssertionError, match="Fidelity drift"):
            calc.get_supply_breakdown()

    def test_shadow_skipped_for_policy_name(self, monkeypatch):
        """Shadow verification is skipped when using policy_name API."""
        calc = SupplyCalculator()
        original_legacy = calc._legacy_compute
        called = []

        def spy_legacy(*args, **kwargs):
            called.append(True)
            return original_legacy(*args, **kwargs)

        monkeypatch.setattr(calc, '_legacy_compute', spy_legacy)

        # policy_name API should NOT trigger legacy compute
        calc.get_supply_breakdown(policy_name="standard")
        assert len(called) == 0


# ---------------------------------------------------------------------------
# New policy_name API
# ---------------------------------------------------------------------------


class TestPolicyNameAPI:
    """Test the new policy_name parameter."""

    def test_standard_policy_name(self):
        """policy_name='standard' returns standard breakdown."""
        calc = SupplyCalculator()
        result = calc.get_supply_breakdown(policy_name="standard")
        assert isinstance(result, SupplyBreakdown)
        assert result.india_eb1_supply == DEFAULT_INDIA_EB1_SUPPLY

    def test_freeze_policy_name(self):
        """policy_name='freeze' returns freeze breakdown with savings."""
        calc = SupplyCalculator()
        result = calc.get_supply_breakdown(policy_name="freeze")
        assert isinstance(result, SupplyBreakdown)
        assert result.fb_savings_freeze > 0

    def test_real_restrictions_policy_name(self):
        """policy_name='real_restrictions' boosts India EB-1."""
        calc = SupplyCalculator()
        result = calc.get_supply_breakdown(policy_name="real_restrictions")
        assert isinstance(result, SupplyBreakdown)
        assert result.india_eb1_supply > DEFAULT_INDIA_EB1_SUPPLY

    def test_unknown_policy_name_raises(self):
        """Unknown policy_name raises ValueError."""
        calc = SupplyCalculator()
        with pytest.raises(ValueError, match="Unknown policy"):
            calc.get_supply_breakdown(policy_name="nonexistent")

    def test_policy_name_matches_boolean_flag(self):
        """policy_name results match equivalent boolean flag results."""
        calc = SupplyCalculator()

        std_flag = calc.get_supply_breakdown(apply_freeze=False, apply_real_restrictions=False)
        std_name = calc.get_supply_breakdown(policy_name="standard")
        assert std_flag.india_eb1_supply == std_name.india_eb1_supply

        freeze_flag = calc.get_supply_breakdown(apply_freeze=True)
        freeze_name = calc.get_supply_breakdown(policy_name="freeze")
        assert freeze_flag.india_eb1_supply == freeze_name.india_eb1_supply

        real_flag = calc.get_supply_breakdown(apply_real_restrictions=True)
        real_name = calc.get_supply_breakdown(policy_name="real_restrictions")
        assert real_flag.india_eb1_supply == real_name.india_eb1_supply
