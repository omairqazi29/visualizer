from datetime import datetime, timedelta
import pandas as pd

class DemandModeler:
    """
    Models visa demand and projects burn rates.
    """
    
    # Burn rate will be derived from data, but we keep a fallback
    DEFAULT_BURN_RATE = 2000 

    def __init__(self, inventory_total: int, burn_rate: int = DEFAULT_BURN_RATE):
        self.inventory_total = inventory_total
        self.burn_rate = burn_rate if burn_rate > 0 else self.DEFAULT_BURN_RATE

    def project_clearance_date(self, start_date: datetime = None, backlog: int = None) -> datetime:
        """
        Projects when a specific backlog amount will be cleared.
        If backlog is None, projects for self.inventory_total.
        """
        if start_date is None:
            start_date = datetime.now()
        
        target_backlog = backlog if backlog is not None else self.inventory_total
        months_required = target_backlog / self.burn_rate
        days_required = months_required * 30.44 # Average days in month
        
        return start_date + timedelta(days=days_required)

    def calculate_confidence_score(self, priority_date: datetime, backlog_ahead: int, target_fy: int = 2027) -> float:
        """
        Calculates a confidence score for approval within a target Fiscal Year.
        Uses backlog_ahead to determine individual position.
        """
        # Project clearance for the specific backlog ahead of this user
        projected_date = self.project_clearance_date(backlog=backlog_ahead)
        target_end_date = datetime(target_fy, 9, 30) # FY ends Sep 30
        
        # Confidence decays as projected date approaches or exceeds target
        if projected_date <= target_end_date:
            # How much buffer do we have?
            buffer_days = (target_end_date - projected_date).days
            if buffer_days > 180:
                return 0.98
            return 0.70 + (0.28 * (buffer_days / 180))
        elif projected_date <= target_end_date + timedelta(days=365):
            # Within a year of target end
            return 0.30 + (0.40 * (1 - (projected_date - target_end_date).days / 365))
        else:
            return 0.10

    @staticmethod
    def calculate_burn_rate_from_dos(dos_df: pd.DataFrame, months: int = 12) -> int:
        """
        Derives an average monthly burn rate from historical DOS issuance data.
        """
        if dos_df is None or dos_df.empty or 'count' not in dos_df.columns:
            return DemandModeler.DEFAULT_BURN_RATE
            
        total_issuances = dos_df['count'].sum()
        # DOS data is usually monthly, but if we have multiple files/months:
        # Assuming the df provided is the aggregation of the requested months
        return int(total_issuances / months) if months > 0 else DemandModeler.DEFAULT_BURN_RATE
