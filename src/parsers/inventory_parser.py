from .base import BaseParser
import pandas as pd
from datetime import datetime

class InventoryParser(BaseParser):
    """
    Parser for USCIS EB Inventory Excel files.
    Specifically handles the India EB-1 'Mountain vs Valley' analysis.
    """
    
    DEPENDENT_MULTIPLIER = 2.2

    def clean(self):
        """Clean and normalize inventory data."""
        super().clean()
        # Ensure we have a datetime column for priority dates
        pd_cols = [c for c in self.df.columns if 'priority' in c or 'date' in c]
        if pd_cols:
            self.df[pd_cols[0]] = pd.to_datetime(self.df[pd_cols[0]], errors='coerce')
            self.df.rename(columns={pd_cols[0]: 'priority_date'}, inplace=True)

    def get_india_eb1_queue(self, cutoff_date: str = '2023-04-01') -> dict:
        """
        Analyzes India EB-1 inventory.
        Returns counts for 'Mountain' (pre-cutoff) and 'Valley' (post-cutoff to end of 2023).
        """
        if self.df is None or 'chargeability' not in self.df.columns:
            return {}

        india_eb1 = self.df[
            (self.df['chargeability'].str.contains('India', case=False, na=False)) &
            (self.df['visa_category'].str.contains('EB1', case=False, na=False))
        ].copy()

        # Apply multiplier
        india_eb1['total_demand'] = india_eb1['count'] * self.DEPENDENT_MULTIPLIER
        
        cutoff = pd.to_datetime(cutoff_date)
        year_end_2023 = pd.to_datetime('2023-12-31')

        mountain = india_eb1[india_eb1['priority_date'] < cutoff]['total_demand'].sum()
        valley = india_eb1[
            (india_eb1['priority_date'] >= cutoff) & 
            (india_eb1['priority_date'] <= year_end_2023)
        ]['total_demand'].sum()

        return {
            "mountain": int(mountain),
            "valley": int(valley),
            "total": int(mountain + valley)
        }
