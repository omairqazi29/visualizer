from .base import BaseParser
import pandas as pd

class DOSParser(BaseParser):
    """
    Parser for DOS Monthly Issuance data.
    Calculates FB usage to determine potential spillover to EB categories.
    """
    
    FB_CATEGORIES = ['F1', 'F2A', 'F2B', 'F3', 'F4', 'FX']

    def clean(self):
        """Clean and normalize DOS specific data."""
        super().clean()
        # DOS files often have 'visa_class' or 'class_of_admission'
        def category_mapper(col: str) -> str:
            if any(h in col.lower() for h in ['class', 'category', 'symbol']):
                return "visa_category"
            return col

        self.df.columns = [category_mapper(c) for c in self.df.columns]
        
        # Normalize the count column
        count_cols = [c for c in self.df.columns if 'count' in c or 'number' in c or 'issuances' in c]
        if count_cols:
            self.normalize_disclosure_values(count_cols)
            # Rename primary count col to 'count'
            self.df.rename(columns={count_cols[0]: 'count'}, inplace=True)

    def get_total_fb_usage(self) -> int:
        """Returns the total issuances for FB categories."""
        if self.df is None or 'visa_category' not in self.df.columns:
            return 0
        
        fb_df = self.df[self.df['visa_category'].isin(self.FB_CATEGORIES)]
        return fb_df['count'].sum()

    def get_fb_spillover(self, statutory_limit: int = 226000) -> int:
        """
        INA 201(c) spillover logic:
        Visas not used in FB (up to the 226k floor) spill over to EB.
        """
        usage = self.get_total_fb_usage()
        # Technically spillover is (480k - usage), but never less than 226k floor.
        # For this model, we look at 'savings' relative to the 226k floor or 
        # higher limits if applicable.
        return max(0, statutory_limit - usage)
