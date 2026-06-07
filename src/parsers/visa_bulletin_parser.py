"""Parser for historical Visa Bulletin FAD/DOF data.

Reads the structured CSV at data/visa_bulletin/india_eb1_history.csv and
computes the historical gap between Date of Filing (DOF) and Final Action
Date (FAD) for India EB-1.  This gap is used to estimate when the DOF will
reach a given priority date, based on the model's FAD prediction.
"""

import os
from datetime import datetime
from statistics import median
from typing import Optional

import pandas as pd

_DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data", "visa_bulletin")
_DEFAULT_FILE = os.path.join(_DATA_DIR, "india_eb1_history.csv")


class VisaBulletinParser:
    """Parses India EB-1 Visa Bulletin history and computes DOF-FAD gap."""

    def __init__(self, file_path: Optional[str] = None):
        self.file_path = file_path or _DEFAULT_FILE
        self._df: Optional[pd.DataFrame] = None

    def _load(self) -> pd.DataFrame:
        if self._df is not None:
            return self._df
        if not os.path.exists(self.file_path):
            raise FileNotFoundError(f"Visa Bulletin data not found: {self.file_path}")
        self._df = pd.read_csv(self.file_path)
        return self._df

    def get_history(self) -> list[dict]:
        """Return all rows as list of dicts with parsed dates."""
        df = self._load()
        rows = []
        for _, r in df.iterrows():
            fad = r["final_action_date"]
            dof = r["date_of_filing"]
            rows.append({
                "bulletin_month": r["bulletin_month"],
                "fad": None if fad == "C" else datetime.strptime(fad, "%Y-%m-%d").date(),
                "dof": None if dof == "C" else datetime.strptime(dof, "%Y-%m-%d").date(),
            })
        return rows

    def compute_gaps(self) -> list[dict]:
        """Compute DOF-FAD gap in months for each bulletin where both exist.

        Returns list of {bulletin_month, fad, dof, gap_months}.
        Only includes months where both FAD and DOF are retrogressed (not Current).
        """
        rows = self.get_history()
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
                "fad": r["fad"],
                "dof": r["dof"],
                "gap_months": gap_months,
            })
        return gaps

    def get_dof_lead_months(self, recent_n: int = 12) -> dict:
        """Compute the DOF lead over FAD from recent Visa Bulletin data.

        Args:
            recent_n: Number of most recent bulletins to use for the estimate.

        Returns:
            dict with:
                median_gap: Median DOF-FAD gap in months (recent N bulletins)
                min_gap: Minimum gap in the window
                max_gap: Maximum gap in the window
                n_datapoints: Number of data points used
                latest_fad: Most recent FAD date in the data
                latest_dof: Most recent DOF date in the data
        """
        gaps = self.compute_gaps()
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
