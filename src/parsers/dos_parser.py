from .base import BaseParser
import pandas as pd
import os

class DOSParser(BaseParser):
    """
    Parser for DOS Monthly Issuance data.
    Calculates FB usage to determine potential spillover to EB categories.
    """
    
    FB_CATEGORIES = ['F1', 'F2A', 'F2B', 'F3', 'F4', 'FX']

    def load_data(self, prevent_recursion: bool = False, **kwargs) -> pd.DataFrame:
        """Overridden to find header automatically for DOS format."""
        if not prevent_recursion:
            self.find_header_row(["Visa Class", "Total"])
        else:
            super().load_data(**kwargs)
        return self.df

    @classmethod
    def load_from_directory(cls, dir_path: str) -> pd.DataFrame:
        """Loads all Excel files in a directory and concatenates them."""
        all_dfs = []
        for file in os.listdir(dir_path):
            if file.endswith('.xlsx'):
                parser = cls(os.path.join(dir_path, file))
                parser.load_data()
                parser.clean()
                if parser.df is not None:
                    all_dfs.append(parser.df)
        
        if not all_dfs:
            return pd.DataFrame()
        
        combined_df = pd.concat(all_dfs, ignore_index=True)
        return combined_df

    def clean(self):
        """Clean and normalize DOS specific data."""
        super().clean()
        # DOS files often have 'visa_class' or 'class_of_admission'
        def category_mapper(col: str) -> str:
            lower_col = col.lower()
            if any(h in lower_col for h in ['class', 'category', 'symbol', 'admission']):
                return "visa_category"
            return col

        self.df.columns = [category_mapper(c) for c in self.df.columns]
        
        # Normalize the count column
        count_cols = [c for c in self.df.columns if 'count' in c or 'number' in c or 'issuances' in c or 'total' in c]
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
        return max(0, statutory_limit - usage)
