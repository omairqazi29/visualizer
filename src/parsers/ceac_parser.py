"""Parser for CEAC (Consular Electronic Application Center) interview scheduling data.

Scraped consular appointment data showing real-time consular pipeline activity.
Validates DOS IV issuance projections by providing ground-truth consulate-level
issuance counts and backlog estimates.

Data sources:
  - visawhen.com (GitHub: underyx/visawhen) — automated scraper that pulls
    consulate-level visa issuance counts and computes backlogs from DOS data.
    NDJSON dumps stored in data/CEAC/:
      * backlogs.ndjson — monthly issuances + backlog by post and visa class
      * post_slugs.ndjson — post slug → consulate name mapping
      * visa_slugs.ndjson — visa slug → class name + description
      * baselines.ndjson — baseline monthly issuances per post + visa class
      * nvc_data.json — NVC case creation/review/inquiry wait times (weekly)

Coverage: Mar 2017 – present (backlogs); Nov 2020 – present (NVC wait times)

Key notes:
  - Data is per-consulate (229 posts worldwide) and per-visa-class.
  - EB visa classes in this dataset: E11 (EB-1A), E12 (EB-1B), E13 (EB-1C),
    E14/E15 (EB-1 spouse/child), EW3 (EB-3 other worker), SD1/SE1/SR1 (EB-4).
  - EB-2 and EB-3 "skilled worker" classes are NOT in this consulate-level dataset.
  - Backlog values are computed estimates (negative = accumulated deficit).
  - India has 5 consulates: Mumbai, Chennai, Hyderabad, Kolkata, New Delhi.
  - This data is COMPLEMENTARY to DOS monthly IV issuance files (which are
    aggregated by country, not by individual consulate).
"""

import json
from pathlib import Path
from typing import Optional


__all__ = ["CEACParser"]


# Visa class slug → EB category mapping
_EB_CATEGORY_MAP = {
    # EB-1
    "e11": "EB1",   # Extraordinary ability
    "e12": "EB1",   # Outstanding professor/researcher
    "e13": "EB1",   # Multinational executive/manager
    "e14": "EB1",   # EB-1 spouse
    "e15": "EB1",   # EB-1 child
    # EB-3 Other Workers
    "ew3": "EW3",   # Other worker
    "ew4": "EW3",   # Spouse of EW3
    "ew5": "EW3",   # Child of EW3
    # EB-4 Special Immigrants
    "sd1": "EB4",   # Minister of religion
    "sd2": "EB4",
    "sd3": "EB4",
    "se1": "EB4",   # US gov employees abroad
    "se2": "EB4",
    "se3": "EB4",
    "sr1": "EB4",   # Religious workers
    "sr2": "EB4",
    "sr3": "EB4",
    "sq1": "EB4",   # Iraqi/Afghan employees
    "sq2": "EB4",
    "sq3": "EB4",
    "si1": "EB4",   # Iraqi/Afghan translators
    "si2": "EB4",
    "si3": "EB4",
    "sk1": "EB4",   # Retired intl org employees
    "sk2": "EB4",
    "sk3": "EB4",
    # EB-5 Investors
    "i51": "EB5",   # Investor (targeted area)
    "i52": "EB5",
    "i53": "EB5",
    "c51": "EB5",   # Investor (non-targeted)
    "c52": "EB5",
    "c53": "EB5",
    "r51": "EB5",   # Regional center
    "r52": "EB5",
    "r53": "EB5",
    "t51": "EB5",   # Targeted rural
    "t52": "EB5",
    "t53": "EB5",
}

# EB-1 principal classes (for issuance counts, excluding derivatives)
_EB1_PRINCIPAL = {"e11", "e12", "e13"}

# All EB-1 classes (including derivatives)
_EB1_ALL = {"e11", "e12", "e13", "e14", "e15"}

# India consulate slugs
_INDIA_POSTS = {"mumbai", "chennai", "hyderabad", "kolkata", "new-delhi"}


class CEACParser:
    """Parser for CEAC consular scheduling and issuance data.

    Reads NDJSON/JSON files from data/CEAC/ and provides aggregated views
    for modeling consular pipeline activity and validating DOS IV projections.
    """

    def __init__(self, data_dir: str = "data/CEAC"):
        self.data_dir = Path(data_dir)
        self._post_names: Optional[dict[str, str]] = None
        self._visa_names: Optional[dict[str, tuple[str, str]]] = None
        self._backlogs: Optional[list[dict]] = None
        self._baselines: Optional[list[dict]] = None
        self._nvc_data: Optional[dict] = None

    # ──────────────────────────────────────────────
    # Loaders
    # ──────────────────────────────────────────────

    def _load_post_names(self) -> dict[str, str]:
        """Load post slug → display name mapping."""
        if self._post_names is not None:
            return self._post_names
        path = self.data_dir / "post_slugs.ndjson"
        if not path.exists():
            self._post_names = {}
            return self._post_names
        self._post_names = {}
        with open(path) as f:
            for line in f:
                row = json.loads(line.strip())
                self._post_names[row[0]] = row[1]
        return self._post_names

    def _load_visa_names(self) -> dict[str, tuple[str, str]]:
        """Load visa slug → (class_name, description) mapping."""
        if self._visa_names is not None:
            return self._visa_names
        path = self.data_dir / "visa_slugs.ndjson"
        if not path.exists():
            self._visa_names = {}
            return self._visa_names
        self._visa_names = {}
        with open(path) as f:
            for line in f:
                row = json.loads(line.strip())
                desc = row[2] if len(row) > 2 else ""
                self._visa_names[row[0]] = (row[1], desc)
        return self._visa_names

    def _load_backlogs(self) -> list[dict]:
        """Load backlogs NDJSON — the core issuance + backlog time series."""
        if self._backlogs is not None:
            return self._backlogs
        path = self.data_dir / "backlogs.ndjson"
        if not path.exists():
            self._backlogs = []
            return self._backlogs
        self._backlogs = []
        with open(path) as f:
            for line in f:
                row = json.loads(line.strip())
                self._backlogs.append({
                    "post": row[0],
                    "visa": row[1],
                    "month": row[2][:10],  # "2024-01-01"
                    "issuances": row[3] if row[3] is not None else 0,
                    "backlog": row[4],
                    "months_ahead": row[5],
                    "expected_delta": row[6],
                })
        return self._backlogs

    def _load_baselines(self) -> list[dict]:
        """Load baseline monthly issuances per post + visa class."""
        if self._baselines is not None:
            return self._baselines
        path = self.data_dir / "baselines.ndjson"
        if not path.exists():
            self._baselines = []
            return self._baselines
        self._baselines = []
        with open(path) as f:
            for line in f:
                row = json.loads(line.strip())
                self._baselines.append({
                    "post": row[0],
                    "visa": row[1],
                    "baseline_monthly": row[2],
                })
        return self._baselines

    def _load_nvc(self) -> dict:
        """Load NVC wait time data (creation/review/inquiry queues)."""
        if self._nvc_data is not None:
            return self._nvc_data
        path = self.data_dir / "nvc_data.json"
        if not path.exists():
            self._nvc_data = {}
            return self._nvc_data
        with open(path) as f:
            self._nvc_data = json.load(f)
        return self._nvc_data

    # ──────────────────────────────────────────────
    # Core EB queries
    # ──────────────────────────────────────────────

    def get_eb_issuances_by_post(self, posts: Optional[set[str]] = None) -> list[dict]:
        """Monthly EB-1 issuance time series aggregated by post.

        Returns list of dicts:
          [{"post": "mumbai", "post_name": "Mumbai", "month": "2024-01",
            "eb1_issuances": 0, "eb1_backlog": -38.3, ...}, ...]

        If posts is None, returns all posts that have EB data.
        """
        backlogs = self._load_backlogs()
        post_names = self._load_post_names()

        # Aggregate by (post, month) for EB-1 classes
        agg: dict[tuple[str, str], dict] = {}
        for row in backlogs:
            if row["visa"] not in _EB1_ALL:
                continue
            if posts and row["post"] not in posts:
                continue
            key = (row["post"], row["month"][:7])  # YYYY-MM
            if key not in agg:
                agg[key] = {
                    "post": row["post"],
                    "post_name": post_names.get(row["post"], row["post"]),
                    "month": row["month"][:7],
                    "eb1_issuances": 0,
                    "eb1_principal_issuances": 0,
                }
            agg[key]["eb1_issuances"] += row["issuances"]
            if row["visa"] in _EB1_PRINCIPAL:
                agg[key]["eb1_principal_issuances"] += row["issuances"]

        result = sorted(agg.values(), key=lambda x: (x["post"], x["month"]))
        return result

    def get_india_eb1_consulate_activity(self) -> list[dict]:
        """India EB-1 issuance time series across all 5 Indian consulates.

        Returns monthly issuances aggregated across Mumbai, Chennai, Hyderabad,
        Kolkata, and New Delhi.
        """
        return self.get_eb_issuances_by_post(posts=_INDIA_POSTS)

    def get_india_eb1_monthly_total(self) -> list[dict]:
        """India EB-1 issuances summed across all Indian consulates by month.

        Returns list of dicts for time series charts:
          [{"month": "2024-01", "eb1_issuances": 0, "eb1_principal": 0}, ...]
        """
        per_post = self.get_india_eb1_consulate_activity()
        monthly: dict[str, dict] = {}
        for row in per_post:
            m = row["month"]
            if m not in monthly:
                monthly[m] = {"month": m, "eb1_issuances": 0, "eb1_principal": 0}
            monthly[m]["eb1_issuances"] += row["eb1_issuances"]
            monthly[m]["eb1_principal"] += row["eb1_principal_issuances"]
        return sorted(monthly.values(), key=lambda x: x["month"])

    def get_top_posts_by_eb1(self, top_n: int = 20) -> list[dict]:
        """Top consulates by total EB-1 issuances (all time).

        Returns list of dicts:
          [{"post": "mumbai", "post_name": "Mumbai", "total_eb1": 1234,
            "total_principal": 500, "months_active": 80}, ...]
        """
        backlogs = self._load_backlogs()
        post_names = self._load_post_names()

        agg: dict[str, dict] = {}
        for row in backlogs:
            if row["visa"] not in _EB1_ALL:
                continue
            p = row["post"]
            if p not in agg:
                agg[p] = {
                    "post": p,
                    "post_name": post_names.get(p, p),
                    "total_eb1": 0,
                    "total_principal": 0,
                    "months": set(),
                }
            agg[p]["total_eb1"] += row["issuances"]
            if row["visa"] in _EB1_PRINCIPAL:
                agg[p]["total_principal"] += row["issuances"]
            agg[p]["months"].add(row["month"][:7])

        result = []
        for v in agg.values():
            result.append({
                "post": v["post"],
                "post_name": v["post_name"],
                "total_eb1": v["total_eb1"],
                "total_principal": v["total_principal"],
                "months_active": len(v["months"]),
            })
        result.sort(key=lambda x: x["total_eb1"], reverse=True)
        return result[:top_n]

    def get_eb_issuances_by_category(self, posts: Optional[set[str]] = None) -> list[dict]:
        """Monthly issuance time series aggregated by EB category.

        Groups all visa classes into EB1/EW3/EB4/EB5 buckets.

        Returns list of dicts:
          [{"month": "2024-01", "EB1": 100, "EW3": 50, "EB4": 30, "EB5": 10}, ...]
        """
        backlogs = self._load_backlogs()

        monthly: dict[str, dict[str, int]] = {}
        for row in backlogs:
            cat = _EB_CATEGORY_MAP.get(row["visa"])
            if cat is None:
                continue
            if posts and row["post"] not in posts:
                continue
            m = row["month"][:7]
            if m not in monthly:
                monthly[m] = {"month": m, "EB1": 0, "EW3": 0, "EB4": 0, "EB5": 0}
            monthly[m][cat] = monthly[m].get(cat, 0) + row["issuances"]

        return sorted(monthly.values(), key=lambda x: x["month"])

    def get_global_eb1_by_fiscal_year(self) -> list[dict]:
        """Global EB-1 issuances by fiscal year (Oct-Sep).

        Returns list for cross-referencing with DOS IV issuance data:
          [{"fiscal_year": 2024, "total_eb1": 45000, "principal_eb1": 20000,
            "india_eb1": 5000, "india_principal": 2000}, ...]
        """
        backlogs = self._load_backlogs()

        fy_data: dict[int, dict] = {}
        for row in backlogs:
            if row["visa"] not in _EB1_ALL:
                continue
            # Parse month to determine FY
            parts = row["month"].split("-")
            year, month = int(parts[0]), int(parts[1])
            fy = year if month >= 10 else year  # Oct starts new FY
            if month >= 10:
                fy = year + 1

            if fy not in fy_data:
                fy_data[fy] = {
                    "fiscal_year": fy,
                    "total_eb1": 0, "principal_eb1": 0,
                    "india_eb1": 0, "india_principal": 0,
                }
            fy_data[fy]["total_eb1"] += row["issuances"]
            if row["visa"] in _EB1_PRINCIPAL:
                fy_data[fy]["principal_eb1"] += row["issuances"]
            if row["post"] in _INDIA_POSTS:
                fy_data[fy]["india_eb1"] += row["issuances"]
                if row["visa"] in _EB1_PRINCIPAL:
                    fy_data[fy]["india_principal"] += row["issuances"]

        return sorted(fy_data.values(), key=lambda x: x["fiscal_year"])

    # ──────────────────────────────────────────────
    # NVC wait times
    # ──────────────────────────────────────────────

    def get_nvc_wait_times(self) -> dict[str, list[dict]]:
        """NVC case processing wait times (weekly time series).

        Returns dict with three queues:
          {"creation": [{"date": "2020-11-30", "days": 10}, ...],
           "review": [{"date": "2020-11-30", "days": 85}, ...],
           "inquiry": [{"date": "2020-11-30", "days": 7}, ...]}

        Values represent the number of business days NVC is currently taking
        for each stage (case creation, document review, inquiry response).
        """
        nvc = self._load_nvc()
        if not nvc:
            return {}
        result = {}
        for queue_name in ["creation", "review", "inquiry"]:
            if queue_name in nvc:
                result[queue_name] = [
                    {"date": date, "days": days}
                    for date, days in sorted(nvc[queue_name].items())
                ]
        return result

    def get_nvc_latest(self) -> dict[str, int]:
        """Latest NVC wait times (most recent data point for each queue).

        Returns: {"creation": 10, "review": 85, "inquiry": 7}
        """
        nvc = self._load_nvc()
        if not nvc:
            return {}
        result = {}
        for queue_name in ["creation", "review", "inquiry"]:
            if queue_name in nvc and nvc[queue_name]:
                latest_date = max(nvc[queue_name].keys())
                result[queue_name] = nvc[queue_name][latest_date]
        return result

    # ──────────────────────────────────────────────
    # Metadata
    # ──────────────────────────────────────────────

    def get_data_range(self) -> dict:
        """Return the date range and size of the backlogs dataset."""
        backlogs = self._load_backlogs()
        if not backlogs:
            return {"start": None, "end": None, "records": 0, "posts": 0}
        months = sorted(set(r["month"] for r in backlogs))
        posts = set(r["post"] for r in backlogs)
        return {
            "start": months[0],
            "end": months[-1],
            "records": len(backlogs),
            "posts": len(posts),
        }

    def get_india_posts(self) -> list[dict]:
        """Return India consulate metadata."""
        post_names = self._load_post_names()
        return [
            {"slug": slug, "name": post_names.get(slug, slug)}
            for slug in sorted(_INDIA_POSTS)
        ]

    # ──────────────────────────────────────────────
    # Summary
    # ──────────────────────────────────────────────

    def get_summary(self) -> dict:
        """Comprehensive summary for API integration.

        Returns key metrics, date range, and NVC wait times.
        """
        data_range = self.get_data_range()
        fy_data = self.get_global_eb1_by_fiscal_year()
        nvc_latest = self.get_nvc_latest()
        top_posts = self.get_top_posts_by_eb1(top_n=10)

        # Latest complete FY (exclude partial current FY)
        complete_fys = [d for d in fy_data if d["fiscal_year"] <= 2024]
        latest_fy = complete_fys[-1] if complete_fys else {}

        return {
            "data_range": data_range,
            "latest_complete_fy": latest_fy,
            "fiscal_year_data": fy_data,
            "top_posts_eb1": top_posts,
            "nvc_wait_times": nvc_latest,
            "india_posts": self.get_india_posts(),
            "source": "visawhen.com (GitHub: underyx/visawhen) — scraped from DOS consular data",
            "notes": {
                "scope": "Consulate-level IV issuances — complements DOS monthly country-level reports",
                "eb_coverage": "EB-1 (E11/E12/E13 + derivatives), EW3 (other workers), EB-4, EB-5",
                "eb2_eb3_note": "EB-2 and EB-3 skilled worker classes not available in consulate-level data",
                "backlog_computation": "Computed from cumulative issuance deficit vs. baseline rates",
            },
        }
