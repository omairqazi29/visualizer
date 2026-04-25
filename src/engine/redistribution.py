import pandas as pd
from typing import Set

class RedistributionEngine:
    """
    Implements the '75-Country Freeze' redistribution logic.
    Identifies visa savings from restricted countries and converts them into spillover.
    """

    def __init__(self, restricted_countries: Set[str], per_country_cap: float = 0.07):
        self.restricted_countries = {c.lower() for c in restricted_countries}
        self.per_country_cap = per_country_cap

    def apply_freeze(self, df: pd.DataFrame, total_limit: int = 226000, chargeability_col: str = 'chargeability', count_col: str = 'count') -> pd.DataFrame:
        """
        Returns a DataFrame where volumes for restricted countries are adjusted.
        Under a 'freeze', we might zero them out entirely or cap them strictly.
        """
        df_frozen = df.copy()
        cap_value = int(total_limit * self.per_country_cap)
        
        for idx, row in df_frozen.iterrows():
            country = str(row[chargeability_col]).lower()
            val = row[count_col]
            
            if country in self.restricted_countries:
                # In a total 'freeze' scenario, we zero them out to see redistribution potential
                df_frozen.at[idx, count_col] = 0
            elif val > cap_value:
                # Apply standard INA per-country cap to others if they exceed it
                # (Simplified: real INA caps are more complex across categories)
                df_frozen.at[idx, count_col] = cap_value
                
        return df_frozen

    def calculate_savings(self, original_df: pd.DataFrame, frozen_df: pd.DataFrame, count_col: str = 'count') -> int:
        """
        Calculates the total 'saved' visas from the freeze.
        """
        original_total = original_df[count_col].sum()
        frozen_total = frozen_df[count_col].sum()
        return int(original_total - frozen_total)

    @staticmethod
    def get_default_restricted_list() -> Set[str]:
        """
        Returns the default list of restricted countries for the 75-Country Freeze.
        """
        return {
            "Dominican Republic", "Philippines", "Bangladesh", "Vietnam", 
            "Mexico", "China - mainland born", "India"
        }
