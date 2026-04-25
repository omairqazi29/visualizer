from .base import BaseParser
import pandas as pd

class PipelineParser(BaseParser):
    """
    Parser for Form I-140 Performance data.
    """
    
    def load_data(self, prevent_recursion: bool = False, **kwargs) -> pd.DataFrame:
        """Finds header for I-140 performance report."""
        if not prevent_recursion:
            self.find_header_row(["Country", "TOTAL"], max_rows=15)
        else:
            super().load_data(**kwargs)
        return self.df

    def get_india_eb1_backlog(self) -> int:
        """Extracts the India EB-1 backlog from the performance data."""
        if self.df is None:
            return 0
        
        # In this specific report, EB1 is usually a column or a row
        # Let's look at the structure again or assume standard naming
        # Row-based search for 'India'
        india_row = self.df[self.df.iloc[:, 0].str.contains("India", case=False, na=False)]
        if not india_row.empty:
            # Preference Categories are columns: 1st, 2nd, 3rd...
            # We need to find the column for 1st Preference (EB1)
            eb1_cols = [c for c in self.df.columns if "1st" in str(c) or "EB1" in str(c).upper()]
            if eb1_cols:
                val = india_row[eb1_cols[0]].values[0]
                return self._parse_val(val)
        return 0

    def _parse_val(self, val) -> int:
        if pd.isna(val) or val == '-':
            return 0
        if isinstance(val, str):
            val = val.replace(',', '')
        try:
            return int(val)
        except:
            return 0
