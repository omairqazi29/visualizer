"""Parser for USCIS H-1B Cap Registration and Approval data.

H-1B cap registrations and approvals are a leading indicator of future I-140
filings — most India EB-1/2/3 cases flow through H-1B first. By tracking
registration volume, selection rates, and approval country-of-birth shares,
we can model "future demand pressure" on the EB system.

Data sources:
  1. Cap Registration/Selection — USCIS Electronic Registration Process page
     https://www.uscis.gov/working-in-the-united-states/temporary-workers/h-1b-specialty-occupations/h-1b-electronic-registration-process
     Published annually. Hand-curated into data/H1B/h1b_cap_registrations.csv

  2. Approvals by Country of Birth — USCIS "Characteristics of H-1B Specialty
     Occupation Workers" Congressional Reports (annual PDFs)
     https://www.uscis.gov/tools/reports-and-studies
     Published annually. Key tables extracted into data/H1B/h1b_approvals_by_country.csv

Coverage: FY2019–FY2026 (registrations from FY2021 when e-registration began)
"""

import csv
from pathlib import Path
from typing import Optional


__all__ = ["H1BParser"]


class H1BParser:
    """Parser for H-1B cap registration and approval data.

    Reads CSV files from data/H1B/ and provides aggregated views for
    modeling future EB demand pressure from the H-1B pipeline.
    """

    def __init__(self, data_dir: str = "data/H1B"):
        self.data_dir = Path(data_dir)
        self._registrations: Optional[list[dict]] = None
        self._approvals: Optional[list[dict]] = None

    def _load_registrations(self) -> list[dict]:
        """Load H-1B cap registration data from CSV."""
        if self._registrations is not None:
            return self._registrations

        path = self.data_dir / "h1b_cap_registrations.csv"
        if not path.exists():
            self._registrations = []
            return self._registrations

        with open(path, newline="") as f:
            reader = csv.DictReader(f)
            self._registrations = []
            for row in reader:
                self._registrations.append({
                    "fiscal_year": int(row["fiscal_year"]),
                    "total_registrations": int(row["total_registrations"]),
                    "eligible_registrations": int(row["eligible_registrations"]),
                    "unique_beneficiaries": int(row["unique_beneficiaries"]),
                    "multiple_registrations": int(row["multiple_registrations"]),
                    "selected_registrations": int(row["selected_registrations"]),
                })

        self._registrations.sort(key=lambda x: x["fiscal_year"])
        return self._registrations

    def _load_approvals(self) -> list[dict]:
        """Load H-1B approvals by country of birth from CSV."""
        if self._approvals is not None:
            return self._approvals

        path = self.data_dir / "h1b_approvals_by_country.csv"
        if not path.exists():
            self._approvals = []
            return self._approvals

        with open(path, newline="") as f:
            reader = csv.DictReader(f)
            self._approvals = []
            for row in reader:
                self._approvals.append({
                    "fiscal_year": int(row["fiscal_year"]),
                    "country_of_birth": row["country_of_birth"],
                    "approvals": int(row["approvals"]),
                    "initial_approvals": int(row["initial_approvals"]) if row.get("initial_approvals") else 0,
                    "continuing_approvals": int(row["continuing_approvals"]) if row.get("continuing_approvals") else 0,
                })

        self._approvals.sort(key=lambda x: (x["fiscal_year"], x["country_of_birth"]))
        return self._approvals

    # ──────────────────────────────────────────────
    # Public API
    # ──────────────────────────────────────────────

    def get_cap_registrations(self) -> list[dict]:
        """H-1B cap registration and selection data by fiscal year.

        Electronic registration began FY2021. Shows demand volume (registrations)
        vs. available slots (selections) — the gap indicates unmet H-1B demand
        that may seek other visa paths or queue for future years.

        Returns list of dicts:
          [{"fiscal_year": 2026, "total_registrations": 358737,
            "eligible_registrations": 343981, "unique_beneficiaries": 336153,
            "multiple_registrations": 7828, "selected_registrations": 120141,
            "selection_rate": 34.9, "multiple_reg_pct": 2.3}, ...]
        """
        regs = self._load_registrations()
        results = []
        for r in regs:
            eligible = r["eligible_registrations"]
            selected = r["selected_registrations"]
            multiple = r["multiple_registrations"]
            results.append({
                **r,
                "selection_rate": round(selected / eligible * 100, 1) if eligible > 0 else 0,
                "multiple_reg_pct": round(multiple / eligible * 100, 1) if eligible > 0 else 0,
            })
        return results

    def get_approvals_by_country(self) -> list[dict]:
        """H-1B approvals by country of birth and fiscal year.

        Returns all rows including the 'All' total row per FY.

        Returns list of dicts:
          [{"fiscal_year": 2025, "country_of_birth": "India", "approvals": 284106,
            "initial_approvals": 73890, "continuing_approvals": 210216,
            "share_pct": 69.9}, ...]
        """
        approvals = self._load_approvals()
        # Build FY totals for computing shares
        fy_totals: dict[int, int] = {}
        for a in approvals:
            if a["country_of_birth"] == "All":
                fy_totals[a["fiscal_year"]] = a["approvals"]

        results = []
        for a in approvals:
            fy_total = fy_totals.get(a["fiscal_year"], 0)
            results.append({
                **a,
                "share_pct": round(a["approvals"] / fy_total * 100, 1) if fy_total > 0 else 0,
            })
        return results

    def get_india_demand_pressure(self) -> list[dict]:
        """India-specific H-1B demand pressure metrics by fiscal year.

        Combines registration selection rates with India's approval share to
        estimate how many India-born H-1B holders will eventually file I-140s.

        Each approved initial H-1B is a ~2-5 year leading indicator of a future
        I-140 filing (typical H-1B holder files I-140 within first 2-3 years).

        Returns list of dicts:
          [{"fiscal_year": 2025, "india_approvals": 284106,
            "india_initial": 73890, "india_continuing": 210216,
            "india_share_pct": 69.9, "total_approvals": 406348,
            "selected_registrations": 135137, "selection_rate": 28.7}, ...]
        """
        approvals = self._load_approvals()
        regs = self._load_registrations()

        # Index by FY
        india_by_fy: dict[int, dict] = {}
        all_by_fy: dict[int, dict] = {}
        for a in approvals:
            if a["country_of_birth"] == "India":
                india_by_fy[a["fiscal_year"]] = a
            elif a["country_of_birth"] == "All":
                all_by_fy[a["fiscal_year"]] = a

        reg_by_fy: dict[int, dict] = {}
        for r in regs:
            reg_by_fy[r["fiscal_year"]] = r

        results = []
        for fy in sorted(set(list(india_by_fy.keys()) + list(reg_by_fy.keys()))):
            india = india_by_fy.get(fy, {})
            total = all_by_fy.get(fy, {})
            reg = reg_by_fy.get(fy, {})

            total_approvals = total.get("approvals", 0)
            india_approvals = india.get("approvals", 0)

            entry: dict = {
                "fiscal_year": fy,
                "india_approvals": india_approvals,
                "india_initial": india.get("initial_approvals", 0),
                "india_continuing": india.get("continuing_approvals", 0),
                "india_share_pct": round(india_approvals / total_approvals * 100, 1) if total_approvals > 0 else 0,
                "total_approvals": total_approvals,
            }

            if reg:
                eligible = reg.get("eligible_registrations", 0)
                selected = reg.get("selected_registrations", 0)
                entry["selected_registrations"] = selected
                entry["selection_rate"] = round(selected / eligible * 100, 1) if eligible > 0 else 0
                entry["total_registrations"] = reg.get("total_registrations", 0)
                entry["unique_beneficiaries"] = reg.get("unique_beneficiaries", 0)

            # Only include if there's meaningful data (approvals or registrations)
            if india_approvals > 0 or reg:
                results.append(entry)

        results.sort(key=lambda x: x["fiscal_year"])
        return results

    def get_top_countries(self, fiscal_year: Optional[int] = None, top_n: int = 10) -> list[dict]:
        """Top countries by H-1B approvals for a given FY (or latest).

        Excludes the 'All' total row.

        Returns list of dicts:
          [{"country": "India", "approvals": 284106, "share_pct": 69.9}, ...]
        """
        approvals = self._load_approvals()
        if not approvals:
            return []

        if fiscal_year is None:
            fiscal_year = max(a["fiscal_year"] for a in approvals)

        fy_data = [a for a in approvals if a["fiscal_year"] == fiscal_year and a["country_of_birth"] != "All"]
        total_row = [a for a in approvals if a["fiscal_year"] == fiscal_year and a["country_of_birth"] == "All"]
        fy_total = total_row[0]["approvals"] if total_row else sum(a["approvals"] for a in fy_data)

        fy_data.sort(key=lambda x: x["approvals"], reverse=True)

        results = []
        for a in fy_data[:top_n]:
            results.append({
                "country": a["country_of_birth"],
                "approvals": a["approvals"],
                "share_pct": round(a["approvals"] / fy_total * 100, 1) if fy_total > 0 else 0,
            })
        return results

    def get_summary(self) -> dict:
        """High-level summary of H-1B demand pressure data.

        Returns dict with key metrics, coverage info, and demand pressure indicators.
        """
        regs = self._load_registrations()
        approvals = self._load_approvals()

        if not regs and not approvals:
            return {
                "error": "No H-1B data available",
                "registration_years": [],
                "approval_years": [],
            }

        reg_years = sorted(set(r["fiscal_year"] for r in regs))
        approval_years = sorted(set(a["fiscal_year"] for a in approvals if a["country_of_birth"] == "All"))

        # Latest registration data
        latest_reg = regs[-1] if regs else {}
        latest_eligible = latest_reg.get("eligible_registrations", 0)
        latest_selected = latest_reg.get("selected_registrations", 0)

        # Latest India approval data
        india_rows = [a for a in approvals if a["country_of_birth"] == "India"]
        latest_india = india_rows[-1] if india_rows else {}
        all_rows = [a for a in approvals if a["country_of_birth"] == "All"]
        latest_all = all_rows[-1] if all_rows else {}

        # India YoY growth
        india_yoy = None
        if len(india_rows) >= 2:
            prev = india_rows[-2]["approvals"]
            curr = india_rows[-1]["approvals"]
            if prev > 0:
                india_yoy = round((curr - prev) / prev * 100, 1)

        # Registration trend (latest vs previous)
        reg_yoy = None
        if len(regs) >= 2:
            prev_reg = regs[-2]["total_registrations"]
            curr_reg = regs[-1]["total_registrations"]
            if prev_reg > 0:
                reg_yoy = round((curr_reg - prev_reg) / prev_reg * 100, 1)

        return {
            "registration_years": reg_years,
            "approval_years": approval_years,
            "latest_reg_fy": latest_reg.get("fiscal_year"),
            "latest_total_registrations": latest_reg.get("total_registrations", 0),
            "latest_selected": latest_selected,
            "latest_selection_rate": round(latest_selected / latest_eligible * 100, 1) if latest_eligible > 0 else 0,
            "latest_unique_beneficiaries": latest_reg.get("unique_beneficiaries", 0),
            "latest_approval_fy": latest_india.get("fiscal_year"),
            "latest_india_approvals": latest_india.get("approvals", 0),
            "latest_india_initial": latest_india.get("initial_approvals", 0),
            "latest_india_share_pct": round(latest_india.get("approvals", 0) / latest_all.get("approvals", 1) * 100, 1) if latest_all.get("approvals") else 0,
            "latest_total_approvals": latest_all.get("approvals", 0),
            "india_yoy_growth_pct": india_yoy,
            "registration_yoy_growth_pct": reg_yoy,
            "source": "USCIS H-1B Electronic Registration Process & Characteristics of H-1B Specialty Occupation Workers Congressional Reports",
        }