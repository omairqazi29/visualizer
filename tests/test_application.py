"""Unit tests for application service layer.

Covers:
- SupplyService error wrapping (_ensure_calculator, ValueError → InvalidPolicyError)
- DemandProjectionService error wrapping (_load_demand_data, predict date validation)
- DataSourceService dict shape and error wrapping
"""

import pytest
from unittest.mock import MagicMock, patch

from src.application.supply_service import SupplyService
from src.application.demand_service import DemandProjectionService
from src.application.data_source_service import DataSourceService
from src.domain.exceptions import DataLoadError, InvalidPolicyError


# ---------------------------------------------------------------------------
# SupplyService
# ---------------------------------------------------------------------------


class TestSupplyService:
    """Tests for SupplyService error handling and delegation."""

    def test_ensure_calculator_wraps_error_in_data_load_error(self):
        """_ensure_calculator wraps init failures in DataLoadError."""
        svc = SupplyService()
        with patch(
            "src.application.supply_service.PandasDOSLoader",
            side_effect=RuntimeError("loader init failed"),
        ):
            with pytest.raises(DataLoadError, match="Failed to initialize"):
                svc._ensure_calculator()

    def test_get_supply_breakdown_converts_value_error(self):
        """ValueError from SupplyCalculator._resolve_policy → InvalidPolicyError."""
        svc = SupplyService()
        mock_calc = MagicMock()
        mock_calc.get_supply_breakdown.side_effect = ValueError("Unknown policy: bad")
        svc._calc = mock_calc

        with pytest.raises(InvalidPolicyError, match="Unknown policy"):
            svc.get_supply_breakdown(policy_name="bad")

    def test_get_supply_breakdown_delegates_flags(self):
        """Boolean flags are forwarded to SupplyCalculator."""
        svc = SupplyService()
        mock_calc = MagicMock()
        mock_breakdown = MagicMock()
        mock_breakdown.total_eb_supply = 100
        mock_breakdown.india_eb1_supply = 50
        mock_calc.get_supply_breakdown.return_value = mock_breakdown
        svc._calc = mock_calc

        result = svc.get_supply_breakdown(apply_freeze=True)

        mock_calc.get_supply_breakdown.assert_called_once_with(
            apply_freeze=True,
            apply_real_restrictions=False,
            policy_name=None,
        )
        assert result is mock_breakdown

    def test_get_monthly_distribution_delegates(self):
        """get_monthly_distribution delegates to SupplyCalculator."""
        svc = SupplyService()
        mock_calc = MagicMock()
        mock_calc.get_monthly_distribution.return_value = {1: 0.1, 2: 0.2}
        svc._calc = mock_calc

        result = svc.get_monthly_distribution(country="India", categories=["E11"])

        mock_calc.get_monthly_distribution.assert_called_once_with(
            country="India", categories=["E11"]
        )
        assert result == {1: 0.1, 2: 0.2}


# ---------------------------------------------------------------------------
# DemandProjectionService
# ---------------------------------------------------------------------------


class TestDemandProjectionService:
    """Tests for DemandProjectionService error handling."""

    def test_predict_invalid_date_raises_value_error(self):
        """predict() raises ValueError for unparseable date."""
        svc = DemandProjectionService()
        with pytest.raises(ValueError, match="YYYY-MM-DD"):
            svc.predict("not-a-date")

    def test_predict_invalid_date_no_implicit_chain(self):
        """ValueError from predict() suppresses the strptime chain."""
        svc = DemandProjectionService()
        with pytest.raises(ValueError) as exc_info:
            svc.predict("bad")
        # from None suppresses __cause__
        assert exc_info.value.__cause__ is None

    def test_load_demand_data_wraps_error(self):
        """_load_demand_data wraps non-DataLoadError in DataLoadError."""
        svc = DemandProjectionService()
        with patch(
            "src.application.demand_service.InventoryParser"
        ) as mock_inv:
            mock_inv.latest.side_effect = FileNotFoundError("missing.xlsx")
            with pytest.raises(DataLoadError, match="Failed to load demand data"):
                svc._load_demand_data()

    def test_load_demand_data_reraises_data_load_error(self):
        """_load_demand_data re-raises DataLoadError without wrapping."""
        svc = DemandProjectionService()
        original = DataLoadError("already wrapped")
        with patch(
            "src.application.demand_service.InventoryParser"
        ) as mock_inv:
            mock_inv.latest.side_effect = original
            with pytest.raises(DataLoadError) as exc_info:
                svc._load_demand_data()
            assert exc_info.value is original


# ---------------------------------------------------------------------------
# DataSourceService
# ---------------------------------------------------------------------------


class TestDataSourceService:
    """Tests for DataSourceService dict shape and error handling."""

    def test_get_data_sources_returns_expected_keys(self):
        """get_data_sources returns dict with all required top-level keys."""
        svc = DataSourceService()
        result = svc.get_data_sources()
        assert "dos_directory" in result
        assert "dos_files" in result
        assert "inventory_file" in result
        assert "pipeline_file" in result

    def test_get_data_sources_inventory_shape(self):
        """Inventory file entry has filename, parsed_date, exists keys."""
        svc = DataSourceService()
        result = svc.get_data_sources()
        inv = result["inventory_file"]
        assert "filename" in inv
        assert "parsed_date" in inv
        assert "exists" in inv
        assert inv["filename"].endswith(".xlsx")

    def test_get_data_sources_pipeline_shape(self):
        """Pipeline file entry has filename, parsed_date, exists keys."""
        svc = DataSourceService()
        result = svc.get_data_sources()
        pipe = result["pipeline_file"]
        assert "filename" in pipe
        assert "parsed_date" in pipe
        assert "exists" in pipe
        assert pipe["filename"].endswith(".xlsx")

    def test_get_data_sources_wraps_error(self):
        """Filesystem errors are wrapped in DataLoadError."""
        svc = DataSourceService()
        with patch(
            "src.application.data_source_service.get_dos_dir",
            side_effect=PermissionError("access denied"),
        ):
            with pytest.raises(DataLoadError, match="Failed to load data source"):
                svc.get_data_sources()
