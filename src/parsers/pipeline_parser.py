from .base import BaseParser
import pandas as pd

from ..data_discovery import get_latest_pipeline_path
from ..constants import (
    EB1_DEPENDENT_MULTIPLIER,
    EB2_DEPENDENT_MULTIPLIER,
    EB3_DEPENDENT_MULTIPLIER,
    EB45_DEPENDENT_MULTIPLIER,
)


# Column header substrings for each EB category in the I-140 pipeline file
_PIPELINE_COL_MAP = {
    "EB1": "1st",
    "EB2": "2nd",
    "EB3_skilled": "3rd (Professional",   # "3rd (Professional and Skilled)"
    "EB3_other": "3rd (Other",            # "3rd (Other)"
    "EB4": "4th",
    "EB5": "5th",
}

# Category-specific dependent multipliers (DHS Yearbook Table 7)
_CATEGORY_MULTIPLIERS = {
    "EB1": EB1_DEPENDENT_MULTIPLIER,       # 2.5x
    "EB2": EB2_DEPENDENT_MULTIPLIER,       # 2.0x
    "EB3_skilled": EB3_DEPENDENT_MULTIPLIER,  # 2.1x
    "EB3_other": EB3_DEPENDENT_MULTIPLIER,    # 2.1x
    "EB4": EB45_DEPENDENT_MULTIPLIER,      # 1.5x
    "EB5": EB45_DEPENDENT_MULTIPLIER,      # 1.5x
}

# Country row labels in the pipeline file
_PIPELINE_COUNTRIES = ["India", "China", "Mexico", "Philippines", "Rest of the World"]


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

    def _find_col(self, substr: str) -> str | None:
        """Find column whose header contains substr (case-insensitive)."""
        if self.df is None:
            return None
        for c in self.df.columns:
            if substr.lower() in str(c).lower():
                return c
        return None

    def _get_cell(self, country: str, col_substr: str) -> int:
        """Get a single cell value by country row and column substring."""
        if self.df is None:
            return 0
        col = self._find_col(col_substr)
        if col is None:
            return 0
        self.normalize_disclosure_values([col])
        row = self.df[self.df.iloc[:, 0].str.contains(country, case=False, na=False)]
        if row.empty:
            return 0
        val = row[col].values[0]
        try:
            return int(val)
        except (ValueError, TypeError):
            return 0

    def get_india_eb1_backlog(self) -> int:
        """Extracts the India EB-1 backlog from the performance data (with dependent multiplier)."""
        return int(self._get_cell("India", _PIPELINE_COL_MAP["EB1"]) * self.DEPENDENT_MULTIPLIER)

    def get_all_eb_pipeline(self) -> dict[str, dict[str, int]]:
        """Return all EB category pipeline totals (with category-specific dependent multipliers).

        I-140 pipeline counts primary beneficiaries only. Each category uses its own
        multiplier from DHS Yearbook Table 7 (EB-1: 2.5x, EB-2: 2.0x, EB-3: 2.1x, EB-4/5: 1.5x).
        Returns nested dict: {"India": {"EB1": 51480, "EB2": 692658, ...}, ...}
        """
        if self.df is None:
            self.load_data()

        result = {}
        for country in _PIPELINE_COUNTRIES:
            key = "ROW" if "Rest" in country else country
            entry = {}
            for cat_key, col_substr in _PIPELINE_COL_MAP.items():
                val = self._get_cell(country, col_substr)
                if val > 0:
                    mult = _CATEGORY_MULTIPLIERS.get(cat_key, self.DEPENDENT_MULTIPLIER)
                    entry[cat_key] = int(val * mult)
            if entry:
                result[key] = entry
        return result
