"""Parser for USCIS Processing Times by Service Center.

Tracks how fast EB I-485s are actually being adjudicated at each center
(Nebraska, Texas, NBC, Potomac). Published monthly by USCIS, this data
reveals domestic processing bottlenecks that affect how quickly approved
visa numbers translate into actual green cards.

Data source:
  USCIS Processing Times page: https://egov.uscis.gov/processing-times/
  Published monthly. Data stored as CSV in data/USCIS_ProcessingTimes/.

File format:
  CSV with columns:
  - publication_date: YYYY-MM-DD (when USCIS published the update)
  - office_code: NSC, TSC, NBC, PSC
  - office_name: Full service center name
  - form_type: I-485
  - category: EB-1, EB-2, EB-3
  - processing_time_min_months: Lower bound of processing window
  - processing_time_max_months: Upper bound of processing window
  - receipt_date_for_inquiry: If filed before this date, can inquire

Key insights this provides:
  - Which centers are fastest/slowest (bottleneck identification)
  - How processing times trend over time (improving or worsening)
  - The gap between min and max (unpredictability measure)
  - EB category-specific bottlenecks (EB-1 vs EB-2 vs EB-3)
"""

import csv
import glob
from datetime import datetime
from pathlib import Path
from typing import Optional


__all__ = ["ProcessingTimesParser"]

# Service center display order (alphabetical by name)
_CENTER_ORDER = {"NBC": 0, "NSC": 1, "PSC": 2, "TSC": 3}


class ProcessingTimesParser:
    """Parser for USCIS EB I-485 processing times by service center.

    Reads CSV files from data/USCIS_ProcessingTimes/ and provides
    time series, cross-center comparisons, and bottleneck analysis.
    """

    def __init__(self, data_dir: str = "data/USCIS_ProcessingTimes"):
        self.data_dir = Path(data_dir)
        self._cache: Optional[list[dict]] = None

    def _load(self) -> list[dict]:
        """Load and parse all processing times CSV files.

        Returns sorted list of dicts (by date, then center, then category).
        """
        if self._cache is not None:
            return self._cache

        results = []
        pattern = str(self.data_dir / "*.csv")
        files = sorted(glob.glob(pattern))

        for filepath in files:
            try:
                rows = self._parse_csv(filepath)
                results.extend(rows)
            except Exception:
                continue

        # Sort by date, then center order, then category
        results.sort(key=lambda r: (
            r["publication_date"],
            _CENTER_ORDER.get(r["office_code"], 99),
            r["category"],
        ))

        # Deduplicate (same date + center + category)
        seen = set()
        deduped = []
        for r in results:
            key = (r["publication_date"], r["office_code"], r["category"])
            if key not in seen:
                seen.add(key)
                deduped.append(r)

        self._cache = deduped
        return self._cache

    def _parse_csv(self, filepath: str) -> list[dict]:
        """Parse a single CSV file into processing time records."""
        rows = []
        with open(filepath, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                try:
                    pub_date = row["publication_date"].strip()
                    rows.append({
                        "publication_date": pub_date,
                        "office_code": row["office_code"].strip(),
                        "office_name": row["office_name"].strip(),
                        "form_type": row.get("form_type", "I-485").strip(),
                        "category": row["category"].strip(),
                        "processing_time_min_months": float(row["processing_time_min_months"]),
                        "processing_time_max_months": float(row["processing_time_max_months"]),
                        "receipt_date_for_inquiry": row.get("receipt_date_for_inquiry", "").strip(),
                    })
                except (KeyError, ValueError):
                    continue
        return rows

    # ──────────────────────────────────────────────
    # Public API — Time Series
    # ──────────────────────────────────────────────

    def get_time_series(self, category: Optional[str] = None,
                        office_code: Optional[str] = None) -> list[dict]:
        """Return processing times as a time series.

        Optional filters: category (EB-1, EB-2, EB-3) and office_code (NSC, TSC, etc.).
        Returns list sorted chronologically.
        """
        data = self._load()
        if category:
            data = [r for r in data if r["category"] == category]
        if office_code:
            data = [r for r in data if r["office_code"] == office_code]
        return data

    def get_latest(self) -> list[dict]:
        """Return only the most recent publication's data (all centers, all categories)."""
        data = self._load()
        if not data:
            return []
        latest_date = max(r["publication_date"] for r in data)
        return [r for r in data if r["publication_date"] == latest_date]

    # ──────────────────────────────────────────────
    # Public API — Cross-Center Comparison
    # ──────────────────────────────────────────────

    def get_center_comparison(self, category: str = "EB-1") -> list[dict]:
        """Compare processing times across centers for a given category.

        Returns latest snapshot with each center's min/max and relative ranking.
        """
        latest = self.get_latest()
        filtered = [r for r in latest if r["category"] == category]
        # Sort fastest to slowest by midpoint
        filtered.sort(key=lambda r: (r["processing_time_min_months"] + r["processing_time_max_months"]) / 2)
        for i, r in enumerate(filtered):
            r["rank"] = i + 1
            r["midpoint_months"] = round(
                (r["processing_time_min_months"] + r["processing_time_max_months"]) / 2, 1
            )
        return filtered

    def get_all_centers(self) -> list[str]:
        """Return list of unique office codes in the data."""
        data = self._load()
        return sorted(set(r["office_code"] for r in data), key=lambda c: _CENTER_ORDER.get(c, 99))

    # ──────────────────────────────────────────────
    # Public API — Bottleneck Analysis
    # ──────────────────────────────────────────────

    def get_bottleneck_summary(self) -> dict:
        """Compute bottleneck analysis across all centers and categories.

        Returns:
        - fastest_center / slowest_center: For EB-1 (most relevant)
        - avg_processing_months: Weighted average across all centers for each category
        - trend: Whether processing times are generally improving or worsening
        - spread: Average max-min gap (unpredictability measure)
        - by_category: Per-category summary across all centers
        """
        data = self._load()
        if not data:
            return {"error": "No processing times data available", "data_points": 0}

        latest = self.get_latest()
        all_dates = sorted(set(r["publication_date"] for r in data))

        # Per-category aggregation from latest data
        by_category = {}
        for cat in ("EB-1", "EB-2", "EB-3"):
            cat_data = [r for r in latest if r["category"] == cat]
            if not cat_data:
                continue
            avg_min = sum(r["processing_time_min_months"] for r in cat_data) / len(cat_data)
            avg_max = sum(r["processing_time_max_months"] for r in cat_data) / len(cat_data)
            by_category[cat] = {
                "avg_min_months": round(avg_min, 1),
                "avg_max_months": round(avg_max, 1),
                "avg_midpoint_months": round((avg_min + avg_max) / 2, 1),
                "avg_spread_months": round(avg_max - avg_min, 1),
                "centers_count": len(cat_data),
                "fastest_center": min(cat_data, key=lambda r: r["processing_time_min_months"])["office_code"],
                "slowest_center": max(cat_data, key=lambda r: r["processing_time_max_months"])["office_code"],
            }

        # EB-1 specific (most relevant for India EB-1 predictions)
        eb1_latest = [r for r in latest if r["category"] == "EB-1"]
        fastest = min(eb1_latest, key=lambda r: (r["processing_time_min_months"] + r["processing_time_max_months"]) / 2) if eb1_latest else None
        slowest = max(eb1_latest, key=lambda r: (r["processing_time_min_months"] + r["processing_time_max_months"]) / 2) if eb1_latest else None

        # Trend analysis: compare first 3 months avg vs last 3 months avg
        trend = "stable"
        if len(all_dates) >= 6:
            early_dates = set(all_dates[:3])
            late_dates = set(all_dates[-3:])
            early_eb1 = [r for r in data if r["publication_date"] in early_dates and r["category"] == "EB-1"]
            late_eb1 = [r for r in data if r["publication_date"] in late_dates and r["category"] == "EB-1"]
            if early_eb1 and late_eb1:
                early_avg = sum((r["processing_time_min_months"] + r["processing_time_max_months"]) / 2 for r in early_eb1) / len(early_eb1)
                late_avg = sum((r["processing_time_min_months"] + r["processing_time_max_months"]) / 2 for r in late_eb1) / len(late_eb1)
                if late_avg > early_avg * 1.05:
                    trend = "worsening"
                elif late_avg < early_avg * 0.95:
                    trend = "improving"

        return {
            "publication_date": all_dates[-1] if all_dates else None,
            "data_points": len(data),
            "months_of_data": len(all_dates),
            "coverage": f"{all_dates[0]} to {all_dates[-1]}" if all_dates else "none",
            "centers": self.get_all_centers(),
            "eb1_fastest_center": fastest["office_code"] if fastest else None,
            "eb1_fastest_center_name": fastest["office_name"] if fastest else None,
            "eb1_fastest_midpoint": round((fastest["processing_time_min_months"] + fastest["processing_time_max_months"]) / 2, 1) if fastest else None,
            "eb1_slowest_center": slowest["office_code"] if slowest else None,
            "eb1_slowest_center_name": slowest["office_name"] if slowest else None,
            "eb1_slowest_midpoint": round((slowest["processing_time_min_months"] + slowest["processing_time_max_months"]) / 2, 1) if slowest else None,
            "eb1_trend": trend,
            "by_category": by_category,
        }
