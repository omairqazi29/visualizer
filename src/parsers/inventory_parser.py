from .base import BaseParser
import pandas as pd

from ..data_discovery import get_latest_inventory_path


# Sheet names in USCIS EB I-485 inventory files
_SHEET_MAP = {
    "India_EB1": "India (EB1 EW3 EB4 CRW EB5)",
    "India_EB23": "India (EB2 EB3)",
    "China": "China",
    "ROW": "Rest of the World",
    "Mexico": "Mexico",
    "Philippines": "Philippines",
}

# Category filters (substring matches against Preference Category column)
_CATEGORY_FILTERS = {
    "EB1": "1st",
    "EB2": "2nd",
    "EB3": "3rd",
    "EB4": "4th",
    "EB5": "5th",
    "EW3": "Other Workers",
}


def _parse_val(v) -> int:
    """Parse inventory cell value, handling D/dash/nan."""
    if pd.isna(v) or str(v).strip() in ["-", ""]:
        return 0
    s = str(v).strip().upper()
    if s == "D":
        return 1
    try:
        return int(str(v).replace(",", ""))
    except Exception:
        return 0


class InventoryParser(BaseParser):
    """
    Parser for USCIS EB Inventory Excel files.
    Handles the pivoted format (years as columns).

    Use InventoryParser("explicit/path.xlsx") for tests / pinned data.
    Use InventoryParser.latest(data_dir=...) for runtime / drop-in new data files
    (auto-selects newest by parsed date or mtime under the supplied data_dir).
    """

    # Cache loaded sheets to avoid re-reading the same Excel file
    _sheet_cache: dict[str, pd.DataFrame] = {}

    @classmethod
    def latest(cls, data_dir: str = "data") -> "InventoryParser":
        """Thin wrapper: return parser for the latest discovered (or fallback) inventory file under data_dir."""
        path = get_latest_inventory_path(data_dir)
        return cls(path)

    def _load_sheet(self, sheet_name: str) -> pd.DataFrame:
        """Load a sheet by name, with caching."""
        cache_key = f"{self.file_path}::{sheet_name}"
        if cache_key not in self._sheet_cache:
            self._sheet_cache[cache_key] = pd.read_excel(
                self.file_path, sheet_name=sheet_name, header=3
            )
        return self._sheet_cache[cache_key]

    def _sum_category(self, sheet_name: str, category_substr: str) -> int:
        """Sum all Priority Date Year columns for rows matching category_substr. Returns primary count (no multiplier)."""
        df = self._load_sheet(sheet_name)
        pref_col = self._find_pref_col(df)
        mask = df[pref_col].astype(str).str.contains(category_substr, case=False, na=False)
        filtered = df[mask]
        year_cols = [c for c in df.columns if "Priority Date Year" in str(c) or "Prior Years" in str(c)]
        total = 0
        for col in year_cols:
            total += int(filtered[col].apply(_parse_val).sum())
        return total

    @staticmethod
    def _find_pref_col(df: pd.DataFrame) -> str:
        """Find the Preference Category column."""
        for c in df.columns:
            if "preference" in str(c).lower() or "category" in str(c).lower():
                return c
        return df.columns[1]

    def load_india_eb1(self) -> pd.DataFrame:
        """Loads specifically the India EB1 sheet."""
        self.df = self._load_sheet(_SHEET_MAP["India_EB1"])
        return self.df

    # ──────────────────────────────────────────────
    # All-country / all-category methods
    # ──────────────────────────────────────────────

    def get_all_eb1_backlogs(self) -> dict[str, int]:
        """Return EB-1 pending totals (with dependent multiplier) for each country group.

        Returns dict like {"India": 48156, "China": 8774, "ROW": 69793, "Mexico": ..., "Philippines": ...}
        """
        mult = self.DEPENDENT_MULTIPLIER
        result = {}
        # India EB-1 is in the EB1/EW3/EB4/CRW/EB5 sheet
        result["India"] = int(self._sum_category(_SHEET_MAP["India_EB1"], _CATEGORY_FILTERS["EB1"]) * mult)
        # China, ROW, Mexico, Philippines each have their own sheet
        for key in ["China", "ROW", "Mexico", "Philippines"]:
            result[key] = int(self._sum_category(_SHEET_MAP[key], _CATEGORY_FILTERS["EB1"]) * mult)
        return result

    def get_all_eb_backlogs(self) -> dict[str, dict[str, int]]:
        """Return all EB category backlogs (with multiplier) for each country group.

        Returns nested dict: {"India": {"EB1": 48156, "EB2": 60282, "EB3": 36819, "EB4": 1683, "EB5": 11678}, ...}
        """
        mult = self.DEPENDENT_MULTIPLIER
        result = {}

        # India: EB1/EW3/EB4/EB5 from sheet 1, EB2/EB3 from sheet 2
        india_sheet1 = _SHEET_MAP["India_EB1"]
        india_sheet2 = _SHEET_MAP["India_EB23"]
        result["India"] = {
            "EB1": int(self._sum_category(india_sheet1, _CATEGORY_FILTERS["EB1"]) * mult),
            "EB2": int(self._sum_category(india_sheet2, _CATEGORY_FILTERS["EB2"]) * mult),
            "EB3": int(self._sum_category(india_sheet2, _CATEGORY_FILTERS["EB3"]) * mult),
            "EB4": int(self._sum_category(india_sheet1, _CATEGORY_FILTERS["EB4"]) * mult),
            "EB5": int(self._sum_category(india_sheet1, _CATEGORY_FILTERS["EB5"]) * mult),
        }

        # China, ROW, Mexico, Philippines: all categories in one sheet each
        for key in ["China", "ROW", "Mexico", "Philippines"]:
            sheet = _SHEET_MAP[key]
            result[key] = {}
            for cat_key, cat_filter in _CATEGORY_FILTERS.items():
                if cat_key == "EW3":
                    continue  # skip EW3 (subset of EB3)
                val = self._sum_category(sheet, cat_filter)
                if val > 0:
                    result[key][cat_key] = int(val * mult)

        return result

    # ──────────────────────────────────────────────
    # Legacy method (unchanged interface)
    # ──────────────────────────────────────────────

    def get_india_eb1_queue(
        self, cutoff_month: int = None, cutoff_year: int = None
    ) -> dict:
        """
        Calculates India EB-1 queue by summing all Priority Date Year columns for EB-1 rows.
        Dynamically handles 2016-2025+ reports. cutoff filters PDs strictly before cutoff for 'backlog_ahead'.
        Total always includes full inventory * 2.2x dependents.
        """
        if self.df is None:
            self.load_india_eb1()

        pref_col = self._find_pref_col(self.df)

        eb1_mask = self.df[pref_col].astype(str).str.contains(
            "1st", case=False, na=False
        ) | self.df[pref_col].astype(str).str.contains("EB1", case=False, na=False)
        eb1_df = self.df[eb1_mask].copy()

        year_cols = [
            c
            for c in self.df.columns
            if "Priority Date Year" in str(c) or "Prior Years" in str(c)
        ]

        total_primary = 0
        mountain = 0
        valley = 0

        for col in year_cols:
            col_sum = int(eb1_df[col].apply(_parse_val).sum())
            total_primary += col_sum

            if "Prior Years" in str(col):
                mountain += col_sum
                continue

            try:
                year_str = str(col).split("-")[-1].strip()
                year = int(year_str)
            except Exception:
                valley += col_sum
                continue

            if cutoff_year is not None:
                if year < cutoff_year:
                    mountain += col_sum
                else:
                    valley += col_sum
            else:
                if year <= 2023:
                    mountain += col_sum
                else:
                    valley += col_sum

        mult = self.DEPENDENT_MULTIPLIER
        return {
            "mountain": int(mountain * mult),
            "valley": int(valley * mult),
            "total": int(total_primary * mult),
        }
