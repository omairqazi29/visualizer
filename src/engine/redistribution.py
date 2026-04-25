import pandas as pd
from typing import Set

class RedistributionEngine:
    """
    Implements the '75-Country Freeze' redistribution logic.
    Identifies visa savings from restricted countries and converts them into spillover.
    """

    def __init__(self, restricted_countries: Set[str]):
        self.restricted_countries = {c.lower() for c in restricted_countries}

    def apply_freeze(self, df: pd.DataFrame, chargeability_col: str = 'chargeability', count_col: str = 'count') -> pd.DataFrame:
        """
        Returns a DataFrame where historical volumes for restricted countries are zeroed out.
        """
        df_frozen = df.copy()
        mask = df_frozen[chargeability_col].str.lower().isin(self.restricted_countries)
        df_frozen.loc[mask, count_col] = 0
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
        # Placeholder for the 75 countries. Using examples from the prompt.
        return {
            "Dominican Republic", "Philippines", "Bangladesh", "Vietnam", 
            "Mexico", "China", "India" # Note: India is often restricted in FB
        }
