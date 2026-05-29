"""Application service for demand-side projections.

Thin wrapper combining InventoryParser, PipelineParser, DemandModeler,
and SupplyService to produce demand projections and predictions.
"""

from __future__ import annotations

import logging
from datetime import datetime

from ..domain.exceptions import DataLoadError
from ..engine.demand import DemandModeler
from ..parsers.inventory_parser import InventoryParser
from ..parsers.pipeline_parser import PipelineParser
from .supply_service import SupplyService

logger = logging.getLogger(__name__)


class DemandProjectionService:
    """Orchestrates demand-side projections using supply data.

    Combines inventory/pipeline loading with DemandModeler to produce
    full supply-demand projections and priority-date predictions.
    """

    def __init__(
        self,
        supply_service: SupplyService | None = None,
        data_dir: str = "data",
    ):
        self._supply_svc = supply_service or SupplyService()
        self._data_dir = data_dir

    def _load_demand_data(self) -> tuple[InventoryParser, dict, int]:
        """Load inventory and pipeline data via auto-discovery."""
        try:
            inv_parser = InventoryParser.latest(self._data_dir)
            inv_stats = inv_parser.get_india_eb1_queue()

            pipe_parser = PipelineParser.latest(self._data_dir)
            pipe_parser.load_data()
            pipe_total = pipe_parser.get_india_eb1_backlog()
        except Exception as exc:
            if isinstance(exc, DataLoadError):
                raise
            raise DataLoadError(
                f"Failed to load demand data: {exc}"
            ) from exc

        return inv_parser, inv_stats, pipe_total

    def project_supply_demand(
        self,
        *,
        apply_freeze: bool = False,
        apply_real_restrictions: bool = False,
    ) -> dict:
        """Full supply-demand projection for the /api/supply-demand endpoint.

        Returns dict matching SupplyDemandResponse fields.
        """
        inv_parser, inv_stats, pipe_total = self._load_demand_data()
        total_queue = int(inv_stats["total"] + pipe_total)

        breakdown = self._supply_svc.get_supply_breakdown(
            apply_freeze=apply_freeze,
            apply_real_restrictions=apply_real_restrictions,
        )
        india_eb1_supply = breakdown.india_eb1_supply

        monthly_dist = self._supply_svc.get_monthly_distribution(
            country="India", categories=["E11", "E12", "E13"]
        )

        modeler = DemandModeler(total_queue, int(india_eb1_supply), monthly_dist)
        projection = modeler.project_clearance()

        logger.info(
            "Supply-demand projection: queue=%d supply=%d months=%d",
            total_queue,
            india_eb1_supply,
            projection["months_to_clear"],
        )

        return {
            "inventory": {k: int(v) for k, v in inv_stats.items()},
            "pipeline_total": int(pipe_total),
            "total_queue": total_queue,
            "annual_eb1_supply": int(india_eb1_supply),
            "monthly_inflow": modeler.monthly_inflow,
            "clearance_date": projection["clearance_date"].strftime("%Y-%m-%d"),
            "months_to_clear": int(projection["months_to_clear"]),
            "cleared": projection["cleared"],
            "trajectory": projection["trajectory"],
        }

    def predict(
        self,
        priority_date: str,
        *,
        apply_freeze: bool = False,
        apply_real_restrictions: bool = False,
    ) -> dict:
        """Full prediction for the /api/predict endpoint.

        Returns dict matching PredictResponse fields.

        Raises:
            ValueError: If priority_date format is invalid.
        """
        try:
            pd_dt = datetime.strptime(priority_date, "%Y-%m-%d")
        except ValueError:
            raise ValueError("priority_date must be in YYYY-MM-DD format") from None

        inv_parser, inv_stats_total, pipe_total = self._load_demand_data()
        total_queue = int(inv_stats_total["total"] + pipe_total)

        # Calculate backlog ahead of this priority date
        inv_ahead = inv_parser.get_india_eb1_queue(
            cutoff_month=pd_dt.month, cutoff_year=pd_dt.year
        )

        if pd_dt.year > 2023:
            months_into_pipeline = (pd_dt.year - 2024) * 12 + pd_dt.month
            pipeline_fraction = min(1.0, months_into_pipeline / 24.0)
            backlog_ahead = inv_stats_total["total"] + int(
                pipe_total * pipeline_fraction
            )
        else:
            backlog_ahead = inv_ahead.get("mountain", inv_ahead["total"])

        breakdown = self._supply_svc.get_supply_breakdown(
            apply_freeze=apply_freeze,
            apply_real_restrictions=apply_real_restrictions,
        )
        india_eb1_supply = breakdown.india_eb1_supply

        monthly_dist = self._supply_svc.get_monthly_distribution(
            country="India", categories=["E11", "E12", "E13"]
        )

        modeler = DemandModeler(total_queue, int(india_eb1_supply), monthly_dist)
        target_fy = modeler.default_target_fy()
        score = modeler.calculate_confidence_score(
            pd_dt, backlog_ahead=backlog_ahead, target_fy=target_fy
        )
        projection = modeler.project_clearance(backlog=backlog_ahead)

        logger.info(
            "Prediction: pd=%s backlog_ahead=%d score=%.2f months=%d",
            priority_date,
            backlog_ahead,
            score,
            projection["months_to_clear"],
        )

        return {
            "confidence_score": float(score),
            "backlog_ahead": int(backlog_ahead),
            "total_queue": int(total_queue),
            "annual_eb1_supply": int(india_eb1_supply),
            "monthly_inflow": modeler.monthly_inflow,
            "target_fy": target_fy,
            "projected_clearance_date": projection["clearance_date"].strftime(
                "%Y-%m-%d"
            ),
            "months_to_clear": int(projection["months_to_clear"]),
            "cleared": projection["cleared"],
            "trajectory": projection["trajectory"],
        }
