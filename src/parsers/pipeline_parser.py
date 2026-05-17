from .base import BaseParser
import pandas as pd

from ..data_discovery import get_latest_pipeline_path


class PipelineParser(BaseParser):
    """
    Parser for Form I-140 Performance data.

    Use PipelineParser("explicit/path.xlsx") for tests / pinned data.
    Use PipelineParser.latest(data_dir=...) for runtime / drop-in new pipeline files
    (auto-selects overall newest by date/mtime under the supplied data_dir).
    """

    @classmethod
    def latest(cls, data_dir: str = "data") -> "PipelineParser":
        """Thin wrapper: return parser for the latest discovered (or fallback) pipeline file under data_dir."""
        path = get_latest_pipeline_path(data_dir)
        return cls(path)

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

        # Ensure disclosure values are normalized
        eb1_cols = [
            c for c in self.df.columns if "1st" in str(c) or "EB1" in str(c).upper()
        ]
        if eb1_cols:
            self.normalize_disclosure_values(eb1_cols)

        # Row-based search for 'India'
        india_row = self.df[
            self.df.iloc[:, 0].str.contains("India", case=False, na=False)
        ]
        if not india_row.empty:
            if eb1_cols:
                val = india_row[eb1_cols[0]].values[0]
                return int(val * self.DEPENDENT_MULTIPLIER)
        return 0

    def _parse_val(self, val) -> int:
        # This method is now redundant as we use normalize_disclosure_values
        if pd.isna(val) or val == "-":
            return 0
        if isinstance(val, str):
            val = val.replace(",", "")
        try:
            return int(float(val))
        except:
            return 0
