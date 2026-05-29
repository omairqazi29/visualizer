import pandas as pd
from typing import Set

from ..constants import (
    EB_BASE_LIMIT,
    EB1_STATUTORY_SHARE,
    EB2_STATUTORY_SHARE,
    EB3_STATUTORY_SHARE,
    EB4_STATUTORY_SHARE,
    EB5_STATUTORY_SHARE,
    PER_COUNTRY_CAP,
    DEFAULT_RESTRICTED_COUNTRIES,
)


# ---------------------------------------------------------------------------
# Pure helper functions — usable from both policies and RedistributionEngine
# ---------------------------------------------------------------------------


def apply_freeze_to_df(
    df: pd.DataFrame,
    restricted_countries: Set[str],
    chargeability_col: str = 'chargeability',
    count_col: str = 'count',
) -> pd.DataFrame:
    """Return a copy of *df* with counts zeroed for restricted countries.

    This is a pure function extracted from ``RedistributionEngine.apply_freeze``
    so that domain-layer policies can reuse the logic without instantiating
    the full engine.
    """
    df_frozen = df.copy()
    restricted_lower = {c.lower() for c in restricted_countries}
    for idx, row in df_frozen.iterrows():
        if str(row[chargeability_col]).lower() in restricted_lower:
            df_frozen.at[idx, count_col] = 0
    return df_frozen


def calculate_savings_from_freeze(
    original_df: pd.DataFrame,
    frozen_df: pd.DataFrame,
    count_col: str = 'count',
) -> int:
    """Return total visa savings (original total − frozen total).

    Pure function extracted from ``RedistributionEngine.calculate_savings``.
    """
    return int(original_df[count_col].sum() - frozen_df[count_col].sum())


class RedistributionEngine:
    """
    Implements the '75-Country Freeze' redistribution logic and INA spillover.
    Identifies visa savings from restricted countries and converts them into spillover.
    """

    def __init__(self, restricted_countries: Set[str], per_country_cap: float = PER_COUNTRY_CAP):
        self.restricted_countries = {c.lower() for c in restricted_countries}
        self.per_country_cap = per_country_cap
        self.base_eb_limit = EB_BASE_LIMIT
        self.category_weights = {
            'EB1': EB1_STATUTORY_SHARE,
            'EB2': EB2_STATUTORY_SHARE,
            'EB3': EB3_STATUTORY_SHARE,
            'EB4': EB4_STATUTORY_SHARE,
            'EB5': EB5_STATUTORY_SHARE,
        }

    def calculate_category_limits(self, total_limit: int = None) -> dict:
        limit = total_limit if total_limit is not None else self.base_eb_limit
        return {cat: int(limit * weight) for cat, weight in self.category_weights.items()}

    def apply_freeze(self, df: pd.DataFrame, category: str = 'EB1', total_limit: int = 140000, chargeability_col: str = 'chargeability', count_col: str = 'count') -> pd.DataFrame:
        """
        Returns a DataFrame where volumes for restricted countries are adjusted.
        Under a 'freeze', we zero them out to see redistribution potential.

        Delegates to the module-level ``apply_freeze_to_df`` pure function.
        """
        return apply_freeze_to_df(df, self.restricted_countries, chargeability_col=chargeability_col, count_col=count_col)

    def distribute_spillover(self, demand_df: pd.DataFrame, supply: int, chargeability_col: str = 'chargeability', count_col: str = 'count') -> tuple:
        """
        Distributes supply to demand according to INA 202(a)(2) 7% per-country cap,
        followed by INA 202(a)(5) surplus distribution to backlogged countries (no cap).

        The per-country cap is computed against the passed supply (typically the category
        statutory limit for the current EB category). Each country may receive at most
        7% under the cap in the first pass. Any leftover supply after satisfying the cap
        for all countries is then distributed to countries that still have unmet demand,
        bypassing the cap (this favors the most backlogged countries such as India/China).

        Returns (allocated_df, unused_supply).
        """
        if demand_df.empty or supply <= 0:
            allocated = demand_df.copy()
            if not allocated.empty:
                allocated['allocated'] = 0
            return allocated, supply

        allocated = demand_df.copy()
        allocated['allocated'] = 0
        remaining_supply = supply

        # INA 202(a)(2): per-country cap = 7% of the supply being allocated
        cap_value = int(supply * self.per_country_cap)

        # First pass: enforce 7% cap per country
        for idx, row in allocated.iterrows():
            if remaining_supply <= 0:
                break
            demand = int(row[count_col])
            can_take = min(demand, cap_value, remaining_supply)
            allocated.at[idx, 'allocated'] = can_take
            remaining_supply -= can_take

        # Second pass: surplus to backlogged countries (INA 202(a)(5) bypass)
        if remaining_supply > 0:
            for idx, row in allocated.iterrows():
                if remaining_supply <= 0:
                    break
                still_needed = int(row[count_col]) - int(row['allocated'])
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

        Delegates to the module-level ``calculate_savings_from_freeze`` pure function.
        """
        return calculate_savings_from_freeze(original_df, frozen_df, count_col=count_col)

    @staticmethod
    def get_default_restricted_list() -> Set[str]:
        """
        Returns the default list of restricted countries for the 75-Country Freeze.
        """
        return DEFAULT_RESTRICTED_COUNTRIES.copy()
