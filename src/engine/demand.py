from datetime import datetime, timedelta
import pandas as pd

class DemandModeler:
    """
    Models visa demand using non-linear historical distribution.

    Supports per-FY supply schedules: supply can vary each fiscal year
    based on actual DOS data.  When a FY has no entry in the schedule,
    ``default_supply`` (the latest/best-estimate value) is used.
    """

    def __init__(
        self,
        inventory_total: int,
        annual_supply: int | None = None,
        monthly_distribution: dict | None = None,
        use_uniform_if_high_supply: bool = True,
        *,
        fy_supply: dict[int, int] | None = None,
    ):
        """
        Args:
            inventory_total: Current backlog count (with dependents).
            annual_supply: Single annual supply (legacy; used as default_supply
                when fy_supply is not provided).
            monthly_distribution: {month_num: fraction} from DOS data.
            use_uniform_if_high_supply: Blend toward flat distribution when
                supply is high (DOS can issue faster when numbers available).
            fy_supply: Per-FY supply schedule {fy_year: india_eb1_supply}.
                If provided, the projection uses FY-specific supply and falls
                back to the most recent FY value for future years.
        """
        self.inventory_total = inventory_total
        self.monthly_distribution = monthly_distribution or {m: 1.0 / 12 for m in range(1, 13)}

        # Build per-FY schedule
        if fy_supply:
            self.fy_supply = dict(fy_supply)
            self.default_supply = fy_supply[max(fy_supply)]  # latest FY as fallback
        else:
            self.fy_supply = {}
            self.default_supply = annual_supply or 0

        # For backward compat: expose single annual_supply (latest or explicit)
        self.annual_supply = self.default_supply

        if use_uniform_if_high_supply and self.default_supply > 15000:
            uniform = {m: 1.0 / 12 for m in range(1, 13)}
            blended = {}
            for m in range(1, 13):
                hist = self.monthly_distribution.get(m, 0)
                blended[m] = 0.6 * hist + 0.4 * uniform[m]
            total = sum(blended.values()) or 1
            self.monthly_distribution = {m: v / total for m, v in blended.items()}

    def project_clearance(self, start_date: datetime = None, backlog: int = None) -> dict:
        """
        Projects clearance trajectory and date.
        Returns a dict with 'clearance_date' and 'trajectory' (list of monthly points).
        """
        if start_date is None:
            start_date = datetime.now()
        
        current_backlog = backlog if backlog is not None else self.inventory_total
        trajectory = [{"date": start_date.strftime("%Y-%m-%d"), "backlog": int(current_backlog)}]
        
        current_date = start_date
        max_months = 600  # 50 years safety cap
        months_passed = 0

        # Track annual supply usage per Fiscal Year (Oct 1 - Sep 30)
        fy_issued = 0

        def _current_fy(dt: datetime) -> int:
            return dt.year + 1 if dt.month >= 10 else dt.year

        current_fy_supply = self.fy_supply.get(_current_fy(start_date), self.default_supply)

        while current_backlog > 0 and months_passed < max_months:
            # FY reset in October: look up supply for the new FY
            if current_date.month == 10 and months_passed > 0:
                fy_issued = 0
                current_fy_supply = self.fy_supply.get(_current_fy(current_date), self.default_supply)

            month_percentage = self.monthly_distribution.get(current_date.month, 0.0)
            potential_monthly_issuance = current_fy_supply * month_percentage

            remaining_fy_supply = max(0, current_fy_supply - fy_issued)
            actual_monthly_issuance = min(potential_monthly_issuance, remaining_fy_supply)
            
            if actual_monthly_issuance > 0:
                current_backlog -= actual_monthly_issuance
                fy_issued += actual_monthly_issuance
            
            if current_backlog <= 0.001:
                current_backlog = 0
            
            # Move to next month for the next iteration
            if current_date.month == 12:
                current_date = datetime(current_date.year + 1, 1, 1)
            else:
                current_date = datetime(current_date.year, current_date.month + 1, 1)

            trajectory.append({
                "date": current_date.strftime("%Y-%m-%d"),
                "backlog": int(current_backlog)
            })
            months_passed += 1

        return {
            "clearance_date": current_date,
            "trajectory": trajectory,
            "months_to_clear": months_passed
        }

    def calculate_confidence_score(self, priority_date: datetime, backlog_ahead: int, target_fy: int = 2027) -> float:
        """
        Calculates a confidence score for approval within a target Fiscal Year.
        """
        projection = self.project_clearance(backlog=backlog_ahead)
        projected_date = projection["clearance_date"]
        target_end_date = datetime(target_fy, 9, 30)
        
        if projected_date <= target_end_date:
            buffer_days = (target_end_date - projected_date).days
            if buffer_days > 180:
                return 0.98
            return 0.70 + (0.28 * (buffer_days / 180))
        elif projected_date <= target_end_date + timedelta(days=365):
            return 0.30 + (0.40 * (1 - (projected_date - target_end_date).days / 365))
        else:
            return 0.10
