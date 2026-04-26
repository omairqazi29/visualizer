from datetime import datetime, timedelta
import pandas as pd

class DemandModeler:
    """
    Models visa demand using non-linear historical distribution.
    """
    
    def __init__(self, inventory_total: int, annual_supply: int, monthly_distribution: dict):
        """
        inventory_total: Current backlog count
        annual_supply: Total visas available per FY (base + spillover + savings)
        monthly_distribution: Dict of {month_num: percentage} e.g. {10: 0.05, 9: 0.40}
        """
        self.inventory_total = inventory_total
        self.annual_supply = annual_supply
        self.monthly_distribution = monthly_distribution

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
        # Safety break to prevent infinite loops if supply is 0 or extremely low
        max_months = 600 # 50 years
        months_passed = 0
        
        # Track annual supply usage per Fiscal Year (Oct 1 - Sep 30)
        fy_issued = 0
        
        while current_backlog > 0 and months_passed < max_months:
            # Check for Fiscal Year Reset (October 1st)
            if current_date.month == 10 and (months_passed > 0):
                fy_issued = 0

            # Get issuance for this specific month based on historical distribution.
            # Missing months default to 0 (caller must explicitly provide all relevant months).
            month_percentage = self.monthly_distribution.get(current_date.month, 0.0)
            potential_monthly_issuance = self.annual_supply * month_percentage
            
            # Limit issuance to remaining FY supply
            remaining_fy_supply = max(0, self.annual_supply - fy_issued)
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
