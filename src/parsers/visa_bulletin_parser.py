"""Parser for historical Visa Bulletin FAD/DOF data.

Reads the structured CSV at data/visa_bulletin/india_eb_history.csv and
computes the historical gap between Date of Filing (DOF) and Final Action
Date (FAD) for India EB categories (EB-1, EB-2, EB-3).  This gap is used
to estimate when the DOF will reach a given priority date, based on the
model's FAD prediction.

Date codes in the CSV:
  - ISO date (YYYY-MM-DD): dated cutoff
  - "C": Current (all priority dates are current — treated as no cutoff)
  - "U": Unavailable (category closed for the month — no numbers issued)
"""

import os
from datetime import date, datetime
from statistics import median
from typing import Optional

import pandas as pd

_DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data", "visa_bulletin")
_DEFAULT_FILE = os.path.join(_DATA_DIR, "india_eb_history.csv")
_LEGACY_FILE = os.path.join(_DATA_DIR, "india_eb1_history.csv")
_CHINA_FILE = os.path.join(_DATA_DIR, "china_eb1_history.csv")

# Status codes for FAD/DOF cells
STATUS_DATE = "date"
STATUS_CURRENT = "C"
STATUS_UNAVAILABLE = "U"
STATUS_INVALID = "invalid"
_CURRENT_TOKENS = frozenset({"C", "CURRENT", "N/A", "NA", ""})
_UNAVAILABLE_TOKENS = frozenset({"U", "UNAVAILABLE"})


def _normalize_cell(raw) -> tuple[Optional[date], str]:
    """Parse a FAD/DOF cell into (date_or_none, status).

    Status is one of: "date", "C" (Current), "U" (Unavailable), "invalid".
    Both C and U yield date=None so callers can treat them uniformly for
    advancement math; status distinguishes the reason for the UI/API.
    Unknown non-empty tokens are "invalid" (not silently Current) so bad
    CSV rows surface in status fields instead of masquerading as Current.
    """
    if raw is None or (isinstance(raw, float) and pd.isna(raw)):
        return None, STATUS_CURRENT
    text = str(raw).strip()
    if not text:
        return None, STATUS_CURRENT
    upper = text.upper()
    if upper in _UNAVAILABLE_TOKENS:
        return None, STATUS_UNAVAILABLE
    if upper in _CURRENT_TOKENS:
        return None, STATUS_CURRENT
    # Dated cutoff
    try:
        return datetime.strptime(text, "%Y-%m-%d").date(), STATUS_DATE
    except ValueError:
        return None, STATUS_INVALID


def _row_from_cells(bulletin_month, category, fad_raw, dof_raw) -> dict:
    fad, fad_status = _normalize_cell(fad_raw)
    dof, dof_status = _normalize_cell(dof_raw)
    return {
        "bulletin_month": bulletin_month,
        "category": category,
        "fad": fad,
        "dof": dof,
        "fad_status": fad_status,
        "dof_status": dof_status,
        "fad_unavailable": fad_status == STATUS_UNAVAILABLE,
        "dof_unavailable": dof_status == STATUS_UNAVAILABLE,
    }


class VisaBulletinParser:
    """Parses India EB Visa Bulletin history and computes DOF-FAD gap."""

    def __init__(self, file_path: Optional[str] = None, category: str = "EB-1",
                 country: str = "India"):
        if file_path:
            self.file_path = file_path
        elif country == "China":
            self.file_path = _CHINA_FILE
        elif os.path.exists(_DEFAULT_FILE):
            self.file_path = _DEFAULT_FILE
        else:
            self.file_path = _LEGACY_FILE
        self.category = category
        self.country = country
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

        Each row includes fad/dof (date or None) plus fad_status/dof_status
        ("date" | "C" | "U") and fad_unavailable/dof_unavailable booleans.

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
            rows.append(_row_from_cells(
                r["bulletin_month"], cat,
                r["final_action_date"], r["date_of_filing"],
            ))
        return rows

    def get_all_categories_history(self) -> list[dict]:
        """Return all rows across all categories with parsed dates."""
        df = self._load()
        rows = []
        for _, r in df.iterrows():
            rows.append(_row_from_cells(
                r["bulletin_month"],
                r.get("category", self.category),
                r["final_action_date"], r["date_of_filing"],
            ))
        return rows

    def compute_gaps(self, category: Optional[str] = None) -> list[dict]:
        """Compute DOF-FAD gap in months for each bulletin where both exist.

        Returns list of {bulletin_month, category, fad, dof, gap_months}.
        Only includes months where both FAD and DOF are dated cutoffs
        (skips Current and Unavailable months — no meaningful gap).
        """
        rows = self.get_history(category=category)
        gaps = []
        for r in rows:
            if r["fad"] is None or r["dof"] is None:
                continue  # skip Current / Unavailable
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
            # Still surface latest dated FAD/DOF from full history when gaps empty
            # (e.g. category currently Unavailable)
            history = self.get_history(category=category)
            latest_fad = next((r["fad"].isoformat() for r in reversed(history) if r["fad"]), None)
            latest_dof = next((r["dof"].isoformat() for r in reversed(history) if r["dof"]), None)
            return {"median_gap": 0, "min_gap": 0, "max_gap": 0, "n_datapoints": 0,
                    "latest_fad": latest_fad, "latest_dof": latest_dof}

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
            current_fad: Current FAD cutoff (ISO date or None if C/U)
            current_dof: Current DOF cutoff (ISO date or None if C/U)
            fad_status / dof_status: "date" | "C" | "U"
            fad_unavailable / dof_unavailable: bool
            fad_is_current: True if PD can receive a visa number this month
            dof_is_current: True if PD can file I-485 this month
            fad_remaining_months: Months of FAD advancement needed (0 if current; None if U)
            dof_remaining_months: Months of DOF advancement needed (0 if current; None if U)
        """
        pd_date = datetime.strptime(priority_date, "%Y-%m-%d").date() if isinstance(priority_date, str) else priority_date
        history = self.get_history(category=category)
        if not history:
            return {
                "bulletin_month": None,
                "category": category or self.category,
                "current_fad": None,
                "current_dof": None,
                "fad_status": STATUS_CURRENT,
                "dof_status": STATUS_CURRENT,
                "fad_unavailable": False,
                "dof_unavailable": False,
                "fad_is_current": False,
                "dof_is_current": False,
                "fad_remaining_months": None,
                "dof_remaining_months": None,
            }

        latest = history[-1]
        fad = latest["fad"]
        dof = latest["dof"]
        fad_status = latest["fad_status"]
        dof_status = latest["dof_status"]
        fad_unavail = latest["fad_unavailable"]
        dof_unavail = latest["dof_unavailable"]

        # Unavailable = category closed — no PD is "current" for FAD
        if fad_unavail or fad_status == STATUS_UNAVAILABLE:
            fad_current = False
            fad_remaining = None  # unknown until numbers resume — never coerce to 0
        elif fad is None:  # Current (C) or invalid/empty treated as open
            fad_current = fad_status != STATUS_INVALID
            fad_remaining = 0.0 if fad_current else None
        else:
            # DOS convention: PD must be *earlier than* FAD cutoff (strict <)
            fad_current = pd_date < fad
            if fad_current:
                fad_remaining = 0.0
            else:
                # PD on/after cutoff is not current; use min 0.1 mo so UI never
                # shows contradictory "0 mo to go" while not current (PD == FAD).
                days = (pd_date - fad).days
                fad_remaining = max(0.1, round(days / 30.44, 1))

        if dof_unavail or dof_status == STATUS_UNAVAILABLE:
            dof_current = False
            dof_remaining = None
        elif dof is None:
            dof_current = dof_status != STATUS_INVALID
            dof_remaining = 0.0 if dof_current else None
        else:
            dof_current = pd_date < dof
            if dof_current:
                dof_remaining = 0.0
            else:
                days = (pd_date - dof).days
                dof_remaining = max(0.1, round(days / 30.44, 1))

        return {
            "bulletin_month": latest["bulletin_month"],
            "category": category or self.category,
            "current_fad": fad.isoformat() if fad else None,
            "current_dof": dof.isoformat() if dof else None,
            "fad_status": fad_status,
            "dof_status": dof_status,
            "fad_unavailable": fad_unavail,
            "dof_unavailable": dof_unavail,
            "fad_is_current": fad_current,
            "dof_is_current": dof_current,
            # Nullable: None when Unavailable (unknown until numbers resume)
            "fad_remaining_months": fad_remaining,
            "dof_remaining_months": dof_remaining,
        }
