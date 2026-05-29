from datetime import datetime, timedelta

from ..constants import DEFAULT_MONTHLY_INFLOW, DEPENDENT_MULTIPLIER


class DemandModeler:
    """
    Models visa demand using non-linear historical distribution.
    """

    def __init__(
        self,
        inventory_total: int,
        annual_supply: int,
        monthly_distribution: dict[int, float],
        use_uniform_if_high_supply: bool = True,
        inflow_rate: int | None = None,
    ):
        """
        inventory_total: Current backlog count (with 2.2x dependents)
        annual_supply: Total visas available per FY (base + spillover + savings)
        monthly_distribution: Dict of {month_num: percentage} e.g. {10: 0.05, 9: 0.40}
          NOTE: Historical % from DOS may under-estimate under restriction scenarios (supply-constrained history).
          When use_uniform_if_high_supply and annual_supply high, blends toward flat monthly.
        inflow_rate: Monthly new cases added to backlog (primary I-140 approvals, pre-multiplier).
          Defaults to DEFAULT_MONTHLY_INFLOW (550). Multiplied by DEPENDENT_MULTIPLIER (2.2x)
          internally to get total persons/month added (~1210/month).
        """
        self.inventory_total = inventory_total
        self.annual_supply = annual_supply
        self.monthly_distribution = monthly_distribution
        primary_inflow = (
            inflow_rate if inflow_rate is not None else DEFAULT_MONTHLY_INFLOW
        )
        if primary_inflow < 0:
            raise ValueError("inflow_rate must be non-negative")
        self.monthly_inflow = int(primary_inflow * DEPENDENT_MULTIPLIER)
        if use_uniform_if_high_supply and annual_supply > 15000:
            # Blend historical with uniform for optimistic high-supply freeze scenarios (INA research: DOS can issue faster when numbers available)
            uniform = {m: 1.0 / 12 for m in range(1, 13)}
            blended = {}
            for m in range(1, 13):
                hist = monthly_distribution.get(m, 0)
                blended[m] = 0.6 * hist + 0.4 * uniform[m]
            total = sum(blended.values()) or 1
            self.monthly_distribution = {m: v / total for m, v in blended.items()}

    def project_clearance(
        self, start_date: datetime | None = None, backlog: int | None = None
    ) -> dict:
        """
        Projects clearance trajectory and date.
        Returns a dict with 'clearance_date' and 'trajectory' (list of monthly points).

        Accounts for:
        - Ongoing India EB-1 I-140 inflows (self.monthly_inflow, default ~1210/month
          with 2.2x multiplier, per FY2025 USCIS quarterly data).
        - Mid-FY start proration: when start_date is not October, the FY supply
          already partially used is estimated so the remaining months don't get
          a full annual allocation before the October reset.

        Assumptions:
        - ``backlog`` reflects current demand *inclusive* of recent inflows.
          Mid-FY proration estimates prior FY supply consumed but does not
          retroactively add inflow for elapsed months (those are already in backlog).
        - If ``backlog`` is 0 with non-zero inflow, the loop does not execute
          (no projection from a zero-backlog starting point).
        """
        if start_date is None:
            # Note: naive datetime (no timezone). In UTC containers, Oct 1 ET
            # may still be Sep 30 UTC. Acceptable for monthly-granularity model.
            start_date = datetime.now()

        current_backlog = backlog if backlog is not None else self.inventory_total
        trajectory = [
            {"date": start_date.strftime("%Y-%m-%d"), "backlog": int(current_backlog)}
        ]

        current_date = start_date
        # Safety break to prevent infinite loops if supply is 0 or extremely low
        max_months = 600  # 50 years
        months_passed = 0

        # Track annual supply usage per Fiscal Year (Oct 1 - Sep 30)
        # Mid-FY start fix: prorate supply already used before start_date.
        # FY starts in October; if we start mid-FY, estimate months already elapsed
        # and the supply already consumed using historical distribution percentages.
        if start_date.month >= 10:
            elapsed_months_in_fy = start_date.month - 10
        else:
            elapsed_months_in_fy = start_date.month + 2  # Jan=3, Feb=4, ..., Sep=11

        fy_issued = 0.0
        if elapsed_months_in_fy > 0:
            for m_offset in range(elapsed_months_in_fy):
                past_month = start_date.month - elapsed_months_in_fy + m_offset
                if past_month <= 0:
                    past_month += 12
                pct = self.monthly_distribution.get(past_month, 0.0)
                fy_issued += self.annual_supply * pct

        while current_backlog > 0 and months_passed < max_months:
            # Check for Fiscal Year Reset (October 1st)
            if current_date.month == 10 and (months_passed > 0):
                fy_issued = 0

            # Add monthly inflow before supply deduction (models new filings arriving
            # before monthly visa issuances). This ordering modestly inflates the
            # clearance timeline by ~1 month vs. post-deduction inflow.
            current_backlog += self.monthly_inflow

            # Get issuance for this specific month based on historical distribution.
            # Missing months default to 0 (caller must explicitly provide all relevant months).
            month_percentage = self.monthly_distribution.get(current_date.month, 0.0)
            potential_monthly_issuance = self.annual_supply * month_percentage

            # Limit issuance to remaining FY supply and current backlog
            remaining_fy_supply = max(0, self.annual_supply - fy_issued)
            actual_monthly_issuance = min(
                potential_monthly_issuance, remaining_fy_supply, current_backlog
            )

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

            trajectory.append(
                {
                    "date": current_date.strftime("%Y-%m-%d"),
                    "backlog": int(current_backlog),
                }
            )
            months_passed += 1

        return {
            "clearance_date": current_date,
            "trajectory": trajectory,
            "months_to_clear": months_passed,
            "cleared": current_backlog == 0,
        }

    @staticmethod
    def default_target_fy(now: datetime | None = None) -> int:
        """Return the target FY for confidence scoring.

        FY runs Oct 1 - Sep 30 and is named by its ending calendar year.
        Returns the next FY-end that is at least 3 months away so the
        confidence score degrades smoothly near FY boundaries.

        In Jan-Jun of year Y → Y (FY ending Sep Y, ≥3 months away).
        In Jul-Sep of year Y → Y+1 (current FY ends too soon, target next).
        In Oct-Dec of year Y → Y+1 (FY Y+1 ending Sep Y+1, ≥9 months away).

        Pass ``now`` to override the clock (useful for deterministic testing).
        """
        if now is None:
            now = datetime.now()
        if now.month >= 7:
            # Jul-Dec: current FY-end (Sep) is <3 months or already past; target next
            return now.year + 1
        return now.year

    def calculate_confidence_score(
        self, priority_date: datetime, backlog_ahead: int, target_fy: int | None = None
    ) -> float:
        """
        Calculates a confidence score for approval within a target Fiscal Year.
        target_fy defaults to the next full FY from the current date (dynamic).
        """
        if target_fy is None:
            target_fy = self.default_target_fy()
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
