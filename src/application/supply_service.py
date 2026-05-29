"""Application service for supply-side visa calculations.

Provides a clean facade over SupplyCalculator + PandasDOSLoader,
eliminating direct access to internal components (e.g., the dos_parser
property leak that previously forced API callers to reach into
SupplyCalculator internals).
"""

import logging
from typing import Optional

from ..adapters.pandas_dos_loader import PandasDOSLoader
from ..domain.exceptions import DataLoadError, InvalidPolicyError
from ..engine.supply import SupplyCalculator, SupplyBreakdown

logger = logging.getLogger(__name__)


class SupplyService:
    """Orchestrates supply-side computations.

    Wraps SupplyCalculator with DI (PandasDOSLoader) and provides
    clean public methods for supply breakdown and monthly distribution.
    Callers no longer need to reach into SupplyCalculator internals.
    """

    def __init__(self, dos_dir: str = "data/DOS"):
        self._dos_dir = dos_dir
        self._calc: Optional[SupplyCalculator] = None

    def _ensure_calculator(self) -> SupplyCalculator:
        """Lazy-init SupplyCalculator with PandasDOSLoader."""
        if self._calc is None:
            try:
                loader = PandasDOSLoader(self._dos_dir)
                self._calc = SupplyCalculator(dos_loader=loader)
            except Exception as exc:
                raise DataLoadError(
                    f"Failed to initialize supply calculator: {exc}"
                ) from exc
        return self._calc

    def get_supply_breakdown(
        self,
        *,
        apply_freeze: bool = False,
        apply_real_restrictions: bool = False,
        policy_name: Optional[str] = None,
    ) -> SupplyBreakdown:
        """Compute supply breakdown for a given policy scenario.

        Accepts either:
        - policy_name: str (one of 'standard', 'freeze', 'real_restrictions')
        - apply_freeze / apply_real_restrictions: bool (legacy compat)

        Raises:
            InvalidPolicyError: Unknown policy name or conflicting arguments.
            DataLoadError: Data loading or computation failure.
        """
        calc = self._ensure_calculator()

        try:
            breakdown = calc.get_supply_breakdown(
                apply_freeze=apply_freeze,
                apply_real_restrictions=apply_real_restrictions,
                policy_name=policy_name,
            )
        except ValueError as exc:
            raise InvalidPolicyError(str(exc)) from exc

        policy_label = policy_name or (
            "freeze" if apply_freeze
            else "real_restrictions" if apply_real_restrictions
            else "standard"
        )
        logger.info(
            "Supply breakdown computed: policy=%s total_eb=%d india_eb1=%d",
            policy_label,
            breakdown.total_eb_supply,
            breakdown.india_eb1_supply,
        )
        return breakdown

    def compute_waterfall(
        self,
        *,
        apply_freeze: bool = False,
        apply_real_restrictions: bool = False,
        policy_name: Optional[str] = None,
    ) -> dict:
        """Compute waterfall-style supply breakdown as a dict.

        Convenience wrapper returning a plain dict matching WaterfallResponse fields.
        """
        b = self.get_supply_breakdown(
            apply_freeze=apply_freeze,
            apply_real_restrictions=apply_real_restrictions,
            policy_name=policy_name,
        )
        return {
            "eb_base_limit": b.eb_base_limit,
            "fb_spillover_std": b.fb_spillover_std,
            "fb_savings_freeze": b.fb_savings_freeze,
            "eb45_spillover_std": b.eb45_spillover_std,
            "eb45_savings_freeze": b.eb45_savings_freeze,
            "total_eb_supply": b.total_eb_supply,
            "eb1_supply": b.eb1_supply,
            "india_eb1_supply": b.india_eb1_supply,
        }

    def get_monthly_distribution(
        self,
        country: str = "India",
        categories: Optional[list[str]] = None,
    ) -> dict[int, float]:
        """Get historical monthly issuance distribution.

        Eliminates the dos_parser property leak: callers access distribution
        data through this method instead of calc.dos_parser.get_monthly_distribution().
        """
        calc = self._ensure_calculator()
        return calc.get_monthly_distribution(country=country, categories=categories)
