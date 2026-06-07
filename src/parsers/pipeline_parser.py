from .base import BaseParser
import pandas as pd

from ..data_discovery import get_latest_pipeline_path
from ..constants import get_data_driven_multipliers


# Column header substrings for each EB category in the I-140 pipeline file
_PIPELINE_COL_MAP = {
    "EB1": "1st",
    "EB2": "2nd",
    "EB3_skilled": "3rd (Professional",   # "3rd (Professional and Skilled)"
    "EB3_other": "3rd (Other",            # "3rd (Other)"
    "EB4": "4th",
    "EB5": "5th",
}


def _get_category_multipliers() -> dict[str, float]:
    """Build pipeline category multipliers from DHS Yearbook Table 7 data.

    Maps pipeline column keys (EB1, EB2, EB3_skilled, EB3_other, EB4, EB5)
    to data-driven multipliers.  Falls back to hardcoded constants if CSV
    is unavailable.
    """
    m = get_data_driven_multipliers()
    return {
        "EB1": m.get("EB1", 2.5),
        "EB2": m.get("EB2", 2.0),
        "EB3_skilled": m.get("EB3", 2.1),
        "EB3_other": m.get("EB3", 2.1),
        "EB4": m.get("EB4", 2.35),
        "EB5": m.get("EB5", 2.55),
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
        multiplier from DHS Yearbook Table 7 data (data-driven, auto-updated).
        Returns nested dict: {"India": {"EB1": 51480, "EB2": 692658, ...}, ...}
        """
        if self.df is None:
            self.load_data()

        cat_multipliers = _get_category_multipliers()
        result = {}
        for country in _PIPELINE_COUNTRIES:
            key = "ROW" if "Rest" in country else country
            entry = {}
            for cat_key, col_substr in _PIPELINE_COL_MAP.items():
                val = self._get_cell(country, col_substr)
                if val > 0:
                    mult = cat_multipliers.get(cat_key, self.DEPENDENT_MULTIPLIER)
                    entry[cat_key] = int(val * mult)
            if entry:
                result[key] = entry
        return result
