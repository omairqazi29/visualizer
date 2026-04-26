import pandas as pd
from typing import Set

class RedistributionEngine:
    """
    Implements the '75-Country Freeze' redistribution logic and INA spillover.
    Identifies visa savings from restricted countries and converts them into spillover.
    """

    def __init__(self, restricted_countries: Set[str], per_country_cap: float = 0.07):
        self.restricted_countries = {c.lower() for c in restricted_countries}
        self.per_country_cap = per_country_cap
        self.base_eb_limit = 140000
        self.category_weights = {
            'EB1': 0.286,
            'EB2': 0.286,
            'EB3': 0.286,
            'EB4': 0.071,
            'EB5': 0.071
        }

    def calculate_category_limits(self, total_limit: int = None) -> dict:
        limit = total_limit if total_limit is not None else self.base_eb_limit
        return {cat: int(limit * weight) for cat, weight in self.category_weights.items()}

    def apply_freeze(self, df: pd.DataFrame, category: str = 'EB1', total_limit: int = 140000, chargeability_col: str = 'chargeability', count_col: str = 'count') -> pd.DataFrame:
        """
        Returns a DataFrame where volumes for restricted countries are adjusted.
        Under a 'freeze', we zero them out to see redistribution potential.
        """
        df_frozen = df.copy()
        cat_limits = self.calculate_category_limits(total_limit)
        cat_limit = cat_limits.get(category, int(total_limit * 0.286))
        
        # INA 7% per-country cap for this category
        cap_value = int(cat_limit * self.per_country_cap)
        
        for idx, row in df_frozen.iterrows():
            country = str(row[chargeability_col]).lower()
            
            if country in self.restricted_countries:
                df_frozen.at[idx, count_col] = 0
                
        return df_frozen

    def distribute_spillover(self, demand_df: pd.DataFrame, supply: int, chargeability_col: str = 'chargeability', count_col: str = 'count') -> tuple:
        """
        Distributes supply to demand according to INA rules (7% cap first, then surplus to backlogged).
        Returns (allocated_df, unused_supply)
        """
        allocated = demand_df.copy()
        allocated['allocated'] = 0
        remaining_supply = supply
        
        # 1. Apply 7% cap strictly first for everyone
        cap_value = int(supply * self.per_country_cap)
        
        for idx, row in allocated.iterrows():
            demand = row[count_col]
            # Use 7% cap
            can_take = min(demand, cap_value, remaining_supply)
            allocated.at[idx, 'allocated'] = can_take
            remaining_supply -= can_take
            
        # 2. If there is remaining supply, distribute to backlogged countries (India/China) 
        # bypassing the 7% cap as per INA 202(a)(5).
        if remaining_supply > 0:
            for idx, row in allocated.iterrows():
                if remaining_supply <= 0: break
                
                still_needed = row[count_col] - row['allocated']
                if still_needed > 0:
                    take_extra = min(still_needed, remaining_supply)
                    allocated.at[idx, 'allocated'] += take_extra
                    remaining_supply -= take_extra
                    
        return allocated, remaining_supply

    def process_all_categories(self, category_demands: dict, total_limit: int = 140000) -> dict:
        """
        Processes all EB categories with vertical spillover.
        category_demands: { 'EB1': df, 'EB2': df, 'EB3': df }
        Returns: { 'EB1': allocated_df, 'EB2': allocated_df, 'EB3': allocated_df, 'unused': int }
        """
        cat_limits = self.calculate_category_limits(total_limit)
        results = {}
        
        # Vertical Spillover: EB1 -> EB2 -> EB3
        # In reality, EB4/5 spill up to EB1, but for this engine we focus on 1/2/3
        
        # Process EB1
        eb1_supply = cat_limits['EB1']
        allocated_eb1, leftover_eb1 = self.distribute_spillover(category_demands.get('EB1', pd.DataFrame()), eb1_supply)
        results['EB1'] = allocated_eb1
        
        # Process EB2 (gets its limit + EB1 spillover)
        eb2_supply = cat_limits['EB2'] + leftover_eb1
        allocated_eb2, leftover_eb2 = self.distribute_spillover(category_demands.get('EB2', pd.DataFrame()), eb2_supply)
        results['EB2'] = allocated_eb2
        
        # Process EB3 (gets its limit + EB2 spillover)
        eb3_supply = cat_limits['EB3'] + leftover_eb2
        allocated_eb3, leftover_eb3 = self.distribute_spillover(category_demands.get('EB3', pd.DataFrame()), eb3_supply)
        results['EB3'] = allocated_eb3
        
        results['unused'] = leftover_eb3
        return results

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
