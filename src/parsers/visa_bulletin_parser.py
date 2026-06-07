"""Parser for historical Visa Bulletin FAD/DOF data.

Reads the structured CSV at data/visa_bulletin/india_eb_history.csv and
computes the historical gap between Date of Filing (DOF) and Final Action
Date (FAD) for India EB categories (EB-1, EB-2, EB-3).  This gap is used
to estimate when the DOF will reach a given priority date, based on the
model's FAD prediction.
"""

import os
from datetime import datetime
from statistics import median
from typing import Optional

import pandas as pd

_DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data", "visa_bulletin")
_DEFAULT_FILE = os.path.join(_DATA_DIR, "india_eb_history.csv")
_LEGACY_FILE = os.path.join(_DATA_DIR, "india_eb1_history.csv")


class VisaBulletinParser:
    """Parses India EB Visa Bulletin history and computes DOF-FAD gap."""

    def __init__(self, file_path: Optional[str] = None, category: str = "EB-1"):
        if file_path:
            self.file_path = file_path
        elif os.path.exists(_DEFAULT_FILE):
            self.file_path = _DEFAULT_FILE
        else:
            self.file_path = _LEGACY_FILE
        self.category = category
        self._df: Optional[pd.DataFrame] = None

    def _load(self) -> pd.DataFrame:
        if self._df is not None:
            return self._df
        if not os.path.exists(self.file_path):
            raise FileNotFoundError(f"Visa Bulletin data not found: {self.file_path}")
        self._df = pd.read_csv(self.file_path)
        return self._df

    def get_history(self, category: Optional[str] = None) -> list[dict]:
        """Return rows as list of dicts with parsed dates, filtered by category.

        Args:
            category: Override the instance category for this call.
                      If None, uses self.category (default "EB-1").
        """
        cat = category or self.category
        df = self._load()
        if "category" in df.columns:
            df = df[df["category"] == cat]
        rows = []
        for _, r in df.iterrows():
            fad = r["final_action_date"]
            dof = r["date_of_filing"]
            rows.append({
                "bulletin_month": r["bulletin_month"],
                "category": cat,
                "fad": None if fad == "C" else datetime.strptime(fad, "%Y-%m-%d").date(),
                "dof": None if dof == "C" else datetime.strptime(dof, "%Y-%m-%d").date(),
            })
        return rows

    def get_all_categories_history(self) -> list[dict]:
        """Return all rows across all categories with parsed dates."""
        df = self._load()
        rows = []
        for _, r in df.iterrows():
            fad = r["final_action_date"]
            dof = r["date_of_filing"]
            rows.append({
                "bulletin_month": r["bulletin_month"],
                "category": r.get("category", self.category),
                "fad": None if fad == "C" else datetime.strptime(fad, "%Y-%m-%d").date(),
                "dof": None if dof == "C" else datetime.strptime(dof, "%Y-%m-%d").date(),
            })
        return rows

    def compute_gaps(self, category: Optional[str] = None) -> list[dict]:
        """Compute DOF-FAD gap in months for each bulletin where both exist.

        Returns list of {bulletin_month, category, fad, dof, gap_months}.
        Only includes months where both FAD and DOF are retrogressed (not Current).
        """
        rows = self.get_history(category=category)
        gaps = []
        for r in rows:
            if r["fad"] is None or r["dof"] is None:
                continue  # skip months where either is Current
            gap_days = (r["dof"] - r["fad"]).days
            if gap_days < 0:
                continue  # skip anomalous data
            gap_months = round(gap_days / 30.44, 1)
            gaps.append({
                "bulletin_month": r["bulletin_month"],
                "category": r.get("category", self.category),
                "fad": r["fad"],
                "dof": r["dof"],
                "gap_months": gap_months,
            })
        return gaps

    def get_dof_lead_months(self, recent_n: int = 12, category: Optional[str] = None) -> dict:
        """Compute the DOF lead over FAD from recent Visa Bulletin data.

        Args:
            recent_n: Number of most recent bulletins to use for the estimate.
            category: EB category to filter by (default: self.category).

        Returns:
            dict with:
                median_gap: Median DOF-FAD gap in months (recent N bulletins)
                min_gap: Minimum gap in the window
                max_gap: Maximum gap in the window
                n_datapoints: Number of data points used
                latest_fad: Most recent FAD date in the data
                latest_dof: Most recent DOF date in the data
        """
        gaps = self.compute_gaps(category=category)
        if not gaps:
            return {"median_gap": 0, "min_gap": 0, "max_gap": 0, "n_datapoints": 0,
                    "latest_fad": None, "latest_dof": None}

        recent = gaps[-recent_n:]
        gap_values = [g["gap_months"] for g in recent]

        return {
            "median_gap": round(median(gap_values), 1),
            "min_gap": min(gap_values),
            "max_gap": max(gap_values),
            "n_datapoints": len(recent),
            "latest_fad": gaps[-1]["fad"].isoformat(),
            "latest_dof": gaps[-1]["dof"].isoformat(),
        }

    def get_current_status(self, priority_date: str, category: Optional[str] = None) -> dict:
        """Check current VB status for a given priority date.

        Args:
            priority_date: Priority date in YYYY-MM-DD format.
            category: EB category to filter by (default: self.category).

        Returns dict with:
            bulletin_month: Latest bulletin month in data
            category: The EB category queried
            current_fad: Current FAD cutoff (ISO date or None if Current)
            current_dof: Current DOF cutoff (ISO date or None if Current)
            fad_is_current: True if PD is before FAD (visa number available)
            dof_is_current: True if PD is before DOF (can file I-485)
            fad_remaining_months: Months of FAD advancement needed (0 if current)
            dof_remaining_months: Months of DOF advancement needed (0 if current)
        """
        from datetime import date
        pd_date = datetime.strptime(priority_date, "%Y-%m-%d").date() if isinstance(priority_date, str) else priority_date
        history = self.get_history(category=category)
        latest = history[-1]

        fad = latest["fad"]
        dof = latest["dof"]

        fad_current = fad is None or pd_date < fad
        dof_current = dof is None or pd_date < dof

        fad_remaining = 0.0
        if fad is not None and not fad_current:
            fad_remaining = round((pd_date - fad).days / 30.44, 1)

        dof_remaining = 0.0
        if dof is not None and not dof_current:
            dof_remaining = round((pd_date - dof).days / 30.44, 1)

        return {
            "bulletin_month": latest["bulletin_month"],
            "category": category or self.category,
            "current_fad": fad.isoformat() if fad else None,
            "current_dof": dof.isoformat() if dof else None,
            "fad_is_current": fad_current,
            "dof_is_current": dof_current,
            "fad_remaining_months": fad_remaining,
            "dof_remaining_months": dof_remaining,
        }
