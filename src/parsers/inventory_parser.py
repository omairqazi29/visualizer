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
        """Return EB-1 pending I-485 totals for each country group.

        NO multiplier applied — the I-485 inventory already counts each person
        individually (principal + derivatives each file their own I-485).
        Returns dict like {"India": 22340, "China": 4513, "ROW": 32286, ...}
        """
        result = {}
        result["India"] = self._sum_category(_SHEET_MAP["India_EB1"], _CATEGORY_FILTERS["EB1"])
        for key in ["China", "ROW", "Mexico", "Philippines"]:
            result[key] = self._sum_category(_SHEET_MAP[key], _CATEGORY_FILTERS["EB1"])
        return result

    def get_all_eb_backlogs(self) -> dict[str, dict[str, int]]:
        """Return all EB category I-485 backlogs for each country group.

        NO multiplier — I-485 inventory already includes dependents.
        Returns nested dict: {"India": {"EB1": 22340, "EB2": 27401, ...}, ...}
        """
        result = {}

        # India: EB1/EW3/EB4/EB5 from sheet 1, EB2/EB3 from sheet 2
        india_sheet1 = _SHEET_MAP["India_EB1"]
        india_sheet2 = _SHEET_MAP["India_EB23"]
        result["India"] = {
            "EB1": self._sum_category(india_sheet1, _CATEGORY_FILTERS["EB1"]),
            "EB2": self._sum_category(india_sheet2, _CATEGORY_FILTERS["EB2"]),
            "EB3": self._sum_category(india_sheet2, _CATEGORY_FILTERS["EB3"]),
            "EB4": self._sum_category(india_sheet1, _CATEGORY_FILTERS["EB4"]),
            "EB5": self._sum_category(india_sheet1, _CATEGORY_FILTERS["EB5"]),
        }

        # China, ROW, Mexico, Philippines: all categories in one sheet each
        for key in ["China", "ROW", "Mexico", "Philippines"]:
            sheet = _SHEET_MAP[key]
            result[key] = {}
            for cat_key, cat_filter in _CATEGORY_FILTERS.items():
                if cat_key == "EW3":
                    continue
                val = self._sum_category(sheet, cat_filter)
                if val > 0:
                    result[key][cat_key] = val

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

        NO multiplier applied — the I-485 inventory already counts each person
        (principal + derivatives) individually. Each count = one visa number needed.
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

        total = 0
        mountain = 0
        valley = 0

        for col in year_cols:
            col_sum = int(eb1_df[col].apply(_parse_val).sum())
            total += col_sum

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

        return {
            "mountain": mountain,
            "valley": valley,
            "total": total,
        }

    # ──────────────────────────────────────────────
    # Cumulative demand for FAD solving
    # ──────────────────────────────────────────────

    # Month name → number mapping for PD Month rows
    _MONTH_NUMBERS: dict[str, int] = {
        "January": 1, "February": 2, "March": 3, "April": 4,
        "May": 5, "June": 6, "July": 7, "August": 8,
        "September": 9, "October": 10, "November": 11, "December": 12,
    }

    def get_cumulative_demand(
        self,
        cutoff_year: int,
        cutoff_month: int,
        category: str = "EB1",
        sheet_key: str | None = None,
    ) -> int:
        """Sum all pending I-485s with priority date strictly before cutoff.

        Uses the PD Year columns and PD Month rows to compute cumulative
        demand.  For years < cutoff_year, ALL months are included.  For the
        cutoff year, only months < cutoff_month are included.  "Prior Years"
        column always counts (pre-dates any cutoff year in the data range).

        Includes BOTH "Available" and "Awaiting Availability" visa status rows.
        NO multiplier applied — I-485 inventory already includes dependents.

        Args:
            cutoff_year:  The year component of the cutoff date.
            cutoff_month: The month component (1-12).  Only PD months
                          *strictly less than* this value are included for
                          the cutoff year.
            category:     EB category key from _CATEGORY_FILTERS (default "EB1").
            sheet_key:    Override _SHEET_MAP key.  If None, auto-selects:
                          "India_EB1" for EB1/EW3/EB4/EB5, "India_EB23" for
                          EB2/EB3.

        Returns:
            Total pending I-485 count with PD before the cutoff.
        """
        # Resolve sheet
        if sheet_key is None:
            if category in ("EB2", "EB3"):
                sheet_key = "India_EB23"
            else:
                sheet_key = "India_EB1"
        sheet_name = _SHEET_MAP[sheet_key]

        df = self._load_sheet(sheet_name)
        pref_col = self._find_pref_col(df)
        cat_substr = _CATEGORY_FILTERS.get(category, category)

        # Filter to matching category rows (both visa statuses)
        mask = df[pref_col].astype(str).str.contains(cat_substr, case=False, na=False)
        filtered = df[mask]

        if filtered.empty:
            return 0

        # Identify year columns
        year_cols = [
            c for c in df.columns
            if "Priority Date Year" in str(c) or "Prior Years" in str(c)
        ]

        # Identify month column
        month_col: str | None = None
        for c in df.columns:
            if "month" in str(c).lower() and "priority" in str(c).lower():
                month_col = c
                break
        if month_col is None:
            # Fallback: use the legacy whole-year sum (no month granularity)
            return self._sum_category(sheet_name, cat_substr)

        total = 0

        for col in year_cols:
            col_str = str(col)

            if "Prior Years" in col_str:
                # Prior Years always before any cutoff — include all rows
                total += int(filtered[col].apply(_parse_val).sum())
                continue

            # Extract year from column header ("Priority Date Year - 2022")
            try:
                col_year = int(col_str.split("-")[-1].strip())
            except (ValueError, IndexError):
                continue

            if col_year < cutoff_year:
                # Entire year is before cutoff — include all months
                total += int(filtered[col].apply(_parse_val).sum())
            elif col_year == cutoff_year:
                # Only include months strictly before cutoff_month
                for idx, row in filtered.iterrows():
                    month_name = str(row[month_col]).strip()
                    month_num = self._MONTH_NUMBERS.get(month_name, 0)
                    if 0 < month_num < cutoff_month:
                        total += _parse_val(row[col])
            # col_year > cutoff_year: skip entirely

        return total
