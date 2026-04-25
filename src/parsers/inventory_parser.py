from .base import BaseParser
import pandas as pd
import numpy as np

class InventoryParser(BaseParser):
    """
    Parser for USCIS EB Inventory Excel files.
    Handles the pivoted format (years as columns).
    """
    
    DEPENDENT_MULTIPLIER = 2.2

    def load_india_eb1(self) -> pd.DataFrame:
        """Loads specifically the India EB1 sheet."""
        self.load_data(sheet_name='India (EB1 EW3 EB4 CRW EB5)', header=3)
        return self.df

    def get_india_eb1_queue(self, cutoff_month: int = 4, cutoff_year: int = 2023) -> dict:
        """
        Calculates India EB1 queue by summing yearly columns.
        """
        if self.df is None:
            self.load_india_eb1()
            
        # Filter for EB1
        eb1_df = self.df[self.df['Preference Category'].str.contains('1st', case=False, na=False)].copy()
        
        # Helper to parse values
        def parse_val(v):
            if pd.isna(v) or v == '-': return 0
            if str(v).strip().upper() == 'D': return 1
            try:
                return int(str(v).replace(',', ''))
            except:
                return 0

        # Sum years before cutoff_year
        year_cols = [c for c in eb1_df.columns if 'Priority Date Year -' in c]
        
        mountain = 0
        valley = 0
        
        for col in year_cols:
            try:
                year_str = col.split('-')[-1].strip()
                if 'Prior Years' in year_str:
                    mountain += eb1_df[col].apply(parse_val).sum()
                    continue
                
                year = int(year_str)
                if year < cutoff_year:
                    mountain += eb1_df[col].apply(parse_val).sum()
                elif year == cutoff_year:
                    # Split by month
                    # Note: This requires looking at 'Priority Date Month' row by row
                    # Or we can simplify if the data is already aggregated
                    # In this report, it seems Month is a row? 
                    # Let's check if 'Priority Date Month' has values like 'January', 'February'...
                    
                    for idx, row in eb1_df.iterrows():
                        month_str = str(row['Priority Date Month']).strip().lower()
                        month_map = {
                            'january': 1, 'february': 2, 'march': 3, 'april': 4,
                            'may': 5, 'june': 6, 'july': 7, 'august': 8,
                            'september': 9, 'october': 10, 'november': 11, 'december': 12
                        }
                        month_num = month_map.get(month_str, 0)
                        
                        val = parse_val(row[col])
                        if month_num < cutoff_month:
                            mountain += val
                        else:
                            valley += val
                elif year == 2023 and cutoff_year == 2023:
                    # If we already handled 2023 above, skip
                    pass
                elif year > cutoff_year and year <= 2023:
                    valley += eb1_df[col].apply(parse_val).sum()
                elif year > 2023:
                    # Post 2023 is usually not in the 'Valley' definition (which is until end of 2023)
                    # but we can include it in 'Pipeline' or 'Total'
                    pass
            except Exception as e:
                print(f"Error parsing column {col}: {e}")

        return {
            "mountain": int(mountain * self.DEPENDENT_MULTIPLIER),
            "valley": int(valley * self.DEPENDENT_MULTIPLIER),
            "total": int((mountain + valley) * self.DEPENDENT_MULTIPLIER)
        }
