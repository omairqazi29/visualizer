from datetime import datetime, timedelta
import pandas as pd

class DemandModeler:
    """
    Models visa demand and projects burn rates.
    """
    
    BURN_RATE_MONTHLY = 2000 # Default burn rate as per prompt
    DEPENDENT_MULTIPLIER = 2.2

    def __init__(self, inventory_total: int, burn_rate: int = BURN_RATE_MONTHLY):
        self.inventory_total = inventory_total
        self.burn_rate = burn_rate

    def project_clearance_date(self, start_date: datetime = None) -> datetime:
        """
        Projects when the current inventory will be cleared.
        """
        if start_date is None:
            start_date = datetime.now()
        
        months_required = self.inventory_total / self.burn_rate
        days_required = months_required * 30.44 # Average days in month
        
        return start_date + timedelta(days=days_required)

    def calculate_confidence_score(self, priority_date: datetime, target_fy: int = 2027) -> float:
        """
        Calculates a confidence score for approval within a target Fiscal Year.
        Heuristic: Earlier PDs relative to projected clearance have higher scores.
        """
        # Simplistic heuristic for demo
        projected_date = self.project_clearance_date()
        target_end_date = datetime(target_fy, 9, 30) # FY ends Sep 30
        
        if projected_date <= target_end_date:
            return 0.95 # High confidence
        elif projected_date <= target_end_date + timedelta(days=180):
            return 0.65 # Medium confidence
        else:
            return 0.25 # Low confidence
