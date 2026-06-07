"""Parser for NVC (National Visa Center) backlog / waiting list data.

The NVC queues cases between I-140 approval and consular interview — a hidden
pipeline stage not captured by the I-485 inventory (AOS path) or the I-140
performance data alone.

Data sources:
- ARIVA (Annual Report of Immigrant Visa Applicants Registered at the NVC):
  Published ~annually by DOS as PDF; we extract into data/NVC/nvc_eb_waiting_list.csv
  and data/NVC/nvc_eb_by_country.csv.
  Source: travel.state.gov → Visa Statistics → Immigrant Visa Statistics
  Latest: Nov 1, 2023 (WaitingListItem_2023_vF.pdf)

- Monthly IV Backlog Report (documentarily-complete cases ready for interview):
  Published as single-page PDFs; extracted into data/NVC/nvc_iv_backlog_monthly.csv.
  Source: travel.state.gov → iv-backlog-report/
  Latest: September 2024

Key notes:
- NVC waiting list counts are for CONSULAR PROCESSING only.
  AOS cases (I-485 pending at USCIS) are NOT included — those are in InventoryParser.
- Figures include principal applicants AND derivatives (spouses/children).
  No multiplier needed (same as I-485 inventory).
- The NVC queue represents a DISJOINT set from I-485 inventory:
  together they form the complete demand picture.
- ~85% of EB immigrants go AOS; ~15% go CP through NVC.
  The NVC numbers are therefore a smaller but distinct demand source.
"""

from pathlib import Path
from typing import Optional

import pandas as pd


# Category mapping: ARIVA uses E1/E2/E3_skilled/E3_other/E4/E5
_EB_CATEGORY_MAP = {
    "E1": "EB1",
    "E2": "EB2",
    "E3_skilled": "EB3",
    "E3_other": "EW3",
    "E4": "EB4",
    "E5": "EB5",
}


class NVCParser:
    """Parser for NVC waiting list and IV backlog data.

    Reads pre-extracted CSV files in data/NVC/ (sourced from DOS ARIVA PDFs).
    """

    def __init__(self, nvc_dir: str = "data/NVC"):
        self.nvc_dir = Path(nvc_dir)
        self._waiting_list_df: Optional[pd.DataFrame] = None
        self._country_df: Optional[pd.DataFrame] = None
        self._monthly_df: Optional[pd.DataFrame] = None

    def _load_waiting_list(self) -> pd.DataFrame:
        """Load the EB waiting list by category and country."""
        if self._waiting_list_df is None:
            path = self.nvc_dir / "nvc_eb_waiting_list.csv"
            if not path.exists():
                raise FileNotFoundError(f"NVC waiting list data not found: {path}")
            self._waiting_list_df = pd.read_csv(path)
        return self._waiting_list_df

    def _load_country(self) -> pd.DataFrame:
        """Load the EB waiting list totals by country."""
        if self._country_df is None:
            path = self.nvc_dir / "nvc_eb_by_country.csv"
            if not path.exists():
                raise FileNotFoundError(f"NVC country data not found: {path}")
            self._country_df = pd.read_csv(path)
        return self._country_df

    def _load_monthly(self) -> pd.DataFrame:
        """Load the monthly IV backlog report data."""
        if self._monthly_df is None:
            path = self.nvc_dir / "nvc_iv_backlog_monthly.csv"
            if not path.exists():
                raise FileNotFoundError(f"NVC monthly backlog data not found: {path}")
            self._monthly_df = pd.read_csv(path)
        return self._monthly_df

    def get_latest_report_date(self) -> str:
        """Return the most recent ARIVA report date as string (e.g. '2023-11-01')."""
        df = self._load_waiting_list()
        return str(df["report_date"].max())

    # ──────────────────────────────────────────────
    # EB category totals (worldwide)
    # ──────────────────────────────────────────────

    def get_eb_totals(self, report_date: Optional[str] = None) -> dict[str, int]:
        """Return NVC EB waiting list totals by category for a given report date.

        Uses 'All Countries' rows. Returns dict like {"EB1": 20582, "EB2": 75567, ...}
        If report_date is None, uses the latest available.
        """
        df = self._load_waiting_list()
        if report_date is None:
            report_date = self.get_latest_report_date()
        mask = (df["report_date"] == report_date) & (df["country"] == "All Countries")
        filtered = df[mask]
        result = {}
        for _, row in filtered.iterrows():
            cat_key = _EB_CATEGORY_MAP.get(row["category"], row["category"])
            result[cat_key] = int(row["applicants"])
        return result

    def get_eb_total_worldwide(self, report_date: Optional[str] = None) -> int:
        """Return the total NVC EB waiting list count (all categories combined)."""
        totals = self.get_eb_totals(report_date)
        return sum(totals.values())

    # ──────────────────────────────────────────────
    # Country-level data
    # ──────────────────────────────────────────────

    def get_eb_by_country(self, report_date: Optional[str] = None) -> dict[str, int]:
        """Return total NVC EB waiting list by country.

        Returns dict like {"India": 48536, "China - mainland born": 65338, ...}
        Excludes 'All Countries' row.
        """
        df = self._load_country()
        if report_date is None:
            report_date = str(df["report_date"].max())
        mask = (df["report_date"] == report_date) & (df["country"] != "All Countries")
        result = {}
        for _, row in df[mask].iterrows():
            result[row["country"]] = int(row["eb_total"])
        return result

    def get_india_eb_nvc(self, report_date: Optional[str] = None) -> dict[str, int]:
        """Return India's NVC EB waiting list breakdown by category.

        These are consular processing cases only (AOS excluded).
        Includes derivatives (no multiplier needed).
        Returns dict like {"EB1": 2426, "EB2": 28921, ...}
        """
        df = self._load_waiting_list()
        if report_date is None:
            report_date = self.get_latest_report_date()
        mask = (df["report_date"] == report_date) & (df["country"] == "India")
        filtered = df[mask]
        result = {}
        for _, row in filtered.iterrows():
            cat_key = _EB_CATEGORY_MAP.get(row["category"], row["category"])
            result[cat_key] = int(row["applicants"])
        return result

    def get_india_eb1_nvc(self, report_date: Optional[str] = None) -> int:
        """Return India EB-1 NVC waiting list count (CP cases only)."""
        india = self.get_india_eb_nvc(report_date)
        return india.get("EB1", 0)

    def get_all_eb_by_country_and_category(
        self, report_date: Optional[str] = None
    ) -> dict[str, dict[str, int]]:
        """Return NVC EB waiting list by country and category.

        Returns nested dict: {"India": {"EB1": 2426, "EB2": 28921, ...}, ...}
        Only includes countries with explicit per-category data (top countries).
        """
        df = self._load_waiting_list()
        if report_date is None:
            report_date = self.get_latest_report_date()
        mask = (
            (df["report_date"] == report_date)
            & (df["country"] != "All Countries")
            & (df["country"] != "All Others")
        )
        result: dict[str, dict[str, int]] = {}
        for _, row in df[mask].iterrows():
            country = row["country"]
            cat_key = _EB_CATEGORY_MAP.get(row["category"], row["category"])
            if country not in result:
                result[country] = {}
            result[country][cat_key] = int(row["applicants"])
        return result

    # ──────────────────────────────────────────────
    # Year-over-year comparison
    # ──────────────────────────────────────────────

    def get_yoy_comparison(self) -> dict[str, dict[str, int]]:
        """Return year-over-year EB category totals for all available report dates.

        Returns: {"2022-11-01": {"EB1": 8818, ...}, "2023-11-01": {"EB1": 20582, ...}}
        """
        df = self._load_waiting_list()
        dates = sorted(df["report_date"].unique())
        result = {}
        for d in dates:
            result[d] = self.get_eb_totals(d)
        return result

    # ──────────────────────────────────────────────
    # Monthly IV Backlog (interview-ready cases)
    # ──────────────────────────────────────────────

    def get_iv_backlog(self) -> dict:
        """Return the latest monthly IV backlog report data.

        This is a SUBSET of the NVC waiting list — only cases that are
        documentarily complete and ready for interview scheduling.

        Returns dict with keys:
        - as_of_date: Date the data reflects
        - documentarily_complete: Total DQ cases at NVC
        - scheduled_interviews: Cases scheduled for that month
        - pending_scheduling: DQ cases still waiting for interview
        """
        df = self._load_monthly()
        if df.empty:
            return {}
        latest = df.iloc[-1]
        return {
            "report_month": str(latest["report_month"]),
            "as_of_date": str(latest["as_of_date"]),
            "documentarily_complete": int(latest["documentarily_complete"]),
            "scheduled_interviews": int(latest["scheduled_interviews"]),
            "pending_scheduling": int(latest["pending_scheduling"]),
        }

    # ──────────────────────────────────────────────
    # Summary for model integration
    # ──────────────────────────────────────────────

    def get_summary(self) -> dict:
        """Return a comprehensive summary for API / model integration.

        Combines ARIVA waiting list + monthly backlog data.
        """
        eb_totals = self.get_eb_totals()
        eb_by_country = self.get_eb_by_country()
        india_eb = self.get_india_eb_nvc()
        iv_backlog = self.get_iv_backlog()

        return {
            "report_date": self.get_latest_report_date(),
            "eb_totals_by_category": eb_totals,
            "eb_total_worldwide": sum(eb_totals.values()),
            "eb_by_country": eb_by_country,
            "india_eb_by_category": india_eb,
            "india_eb_total": sum(india_eb.values()),
            "india_eb1_nvc": india_eb.get("EB1", 0),
            "iv_backlog": iv_backlog,
            "notes": {
                "scope": "Consular processing only; AOS (I-485) excluded",
                "includes_derivatives": True,
                "source": "DOS ARIVA (Annual Report of IV Applicants at NVC)",
                "eb_pct_via_cp": "~15% of EB immigrants use consular processing",
            },
        }
