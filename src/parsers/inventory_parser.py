from .base import BaseParser
import pandas as pd

from ..data_discovery import get_latest_inventory_path
from ..domain.value_objects import IndiaEB1Queue


class InventoryParser(BaseParser):
    """
    Parser for USCIS EB Inventory Excel files.
    Handles the pivoted format (years as columns).

    Use InventoryParser("explicit/path.xlsx") for tests / pinned data.
    Use InventoryParser.latest(data_dir=...) for runtime / drop-in new data files
    (auto-selects newest by parsed date or mtime under the supplied data_dir).
    """

    @classmethod
    def latest(cls, data_dir: str = "data") -> "InventoryParser":
        """Thin wrapper: return parser for the latest discovered (or fallback) inventory file under data_dir."""
        path = get_latest_inventory_path(data_dir)
        return cls(path)

    def load_india_eb1(self) -> pd.DataFrame:
        """Loads specifically the India EB1 sheet."""
        self.load_data(sheet_name="India (EB1 EW3 EB4 CRW EB5)", header=3)
        return self.df

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

        # Robust EB-1 filter: matches "1st" or "EB1" in Preference Category (handles full "Employment-Based 1st Preference Category (EB1)")
        pref_col = None
        for c in self.df.columns:
            if "preference" in str(c).lower() or "category" in str(c).lower():
                pref_col = c
                break
        if pref_col is None:
            pref_col = self.df.columns[1]  # fallback

        eb1_mask = self.df[pref_col].astype(str).str.contains(
            "1st", case=False, na=False
        ) | self.df[pref_col].astype(str).str.contains("EB1", case=False, na=False)
        eb1_df = self.df[eb1_mask].copy()

        def parse_val(v):
            if pd.isna(v) or str(v).strip() in ["-", ""]:
                return 0
            s = str(v).strip().upper()
            if s == "D":
                return 1
            try:
                return int(str(v).replace(",", ""))
            except (ValueError, TypeError):
                return 0

        year_cols = [
            c
            for c in self.df.columns
            if "Priority Date Year" in str(c) or "Prior Years" in str(c)
        ]

        total_primary = 0
        mountain = 0
        valley = 0

        for col in year_cols:
            col_sum = int(eb1_df[col].apply(parse_val).sum())
            total_primary += col_sum

            if "Prior Years" in str(col):
                mountain += col_sum
                continue

            try:
                year_str = str(col).split("-")[-1].strip()
                year = int(year_str)
            except (ValueError, TypeError):
                valley += col_sum
                continue

            if cutoff_year is not None:
                if year < cutoff_year:
                    mountain += col_sum
                else:
                    # Same-year (and later) lumped to valley (not counted as "ahead" for the cutoff PD).
                    # cutoff_month accepted for signature but currently unused (year-granular only;
                    # month-level split possible in future if data requires intra-year precision).
                    valley += col_sum
            else:
                # Legacy default behavior: pre-2024 mountain-ish, rest valley (updated threshold)
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

    def get_india_eb1_queue_typed(
        self, cutoff_month: int = None, cutoff_year: int = None
    ) -> IndiaEB1Queue:
        """Returns India EB-1 queue as an IndiaEB1Queue domain value object.

        Wraps get_india_eb1_queue() for type-safe domain layer usage.
        """
        raw = self.get_india_eb1_queue(
            cutoff_month=cutoff_month, cutoff_year=cutoff_year
        )
        return IndiaEB1Queue(
            mountain=raw["mountain"],
            valley=raw["valley"],
            total=raw["total"],
        )

    def parse(self) -> pd.DataFrame:
        """Parse inventory data: load India EB1 sheet and return the DataFrame.

        Satisfies the Parser protocol from src.domain.protocols.

        NOTE: clean() is intentionally NOT called here. get_india_eb1_queue()
        relies on original cased column names (e.g. "Priority Date Year - 2024",
        "Preference Category") which normalize_headers() would lowercase and break.
        """
        self.load_india_eb1()
        return self.df
