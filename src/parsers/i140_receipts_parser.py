"""Parser for USCIS I-140 Receipts (New Filings) data.

Parses the 'Number of Form I-140 Petitions Received and Current Status'
Excel file published quarterly by USCIS. This data is SEPARATE from the
I-140 performance/pipeline data (approved petitions awaiting visa numbers).

Receipts = new petitions entering the system. Models queue growth rate.

Source: https://www.uscis.gov/tools/reports-and-studies/immigration-and-citizenship-data
File: i140_rec_by_class_country_*.xlsx
"""

from .base import BaseParser
import pandas as pd
from typing import Optional

from ..data_discovery import get_latest_i140_receipts_path


# Sheet name → canonical country key
_SHEET_COUNTRY_MAP = {
    "All Countries": "All",
    "India": "India",
    "China": "China",
    "Philippines": "Philippines",
    "Brazil": "Brazil",
    "Vietnam": "Vietnam",
}


class I140ReceiptsParser(BaseParser):
    """Parser for I-140 Receipts (New Filings) by country, category, and fiscal year.

    Use I140ReceiptsParser("path.xlsx") for tests / pinned data.
    Use I140ReceiptsParser.latest() for runtime auto-discovery.
    """

    @classmethod
    def latest(cls, data_dir: str = "data") -> "I140ReceiptsParser":
        path = get_latest_i140_receipts_path(data_dir)
        return cls(path)

    def _parse_sheet(self, sheet_name: str) -> dict:
        """Parse a single country sheet and return structured receipt data."""
        df = pd.read_excel(self.file_path, sheet_name=sheet_name, header=None)

        # Find header row: the row with multiple numeric fiscal year values (2014, 2015, ...)
        # Must distinguish from subtitle rows like "Fiscal Years 2014 to 2025 (Q1-Q4)"
        header_row = None
        fy_cols = {}  # {fiscal_year: column_index}
        for i in range(min(10, len(df))):
            candidate_cols = {}
            for col_idx, val in enumerate(df.iloc[i].values):
                try:
                    year = int(float(val))
                    if 2010 <= year <= 2030:
                        candidate_cols[year] = col_idx
                except (ValueError, TypeError):
                    continue
            # Require at least 3 numeric year columns to be the real header
            if len(candidate_cols) >= 3:
                header_row = i
                fy_cols = candidate_cols
                break
        if header_row is None:
            return {}

        # Parse data rows below header
        data_rows = df.iloc[header_row + 1:]

        def _get_row_values(label_substr: str, start_row: int = 0) -> Optional[int]:
            """Find row index matching label substring starting from start_row."""
            for idx in range(start_row, len(data_rows)):
                cell = str(data_rows.iloc[idx, 0]).strip()
                if label_substr.lower() in cell.lower():
                    return header_row + 1 + idx
            return None

        def _extract_fy_values(row_idx: int) -> dict[int, int]:
            """Extract fiscal year values from a given row."""
            result = {}
            for fy, col_idx in fy_cols.items():
                try:
                    val = df.iloc[row_idx, col_idx]
                    result[fy] = int(float(val))
                except (ValueError, TypeError):
                    result[fy] = 0
            return result

        # Overall totals
        total_row = _get_row_values("TOTAL")
        approved_row = _get_row_values("Approved") if total_row else None
        denied_row = _get_row_values("Denied") if total_row else None
        pending_row = _get_row_values("Pending") if total_row else None

        result = {"overall": {}}
        if total_row is not None:
            result["overall"]["receipts"] = _extract_fy_values(total_row)
        if approved_row is not None:
            result["overall"]["approved"] = _extract_fy_values(approved_row)
        if denied_row is not None:
            result["overall"]["denied"] = _extract_fy_values(denied_row)
        if pending_row is not None:
            result["overall"]["pending"] = _extract_fy_values(pending_row)

        # EB category breakdowns - find "Total Petitions" rows after each preference header
        categories = {
            "EB1": "First Preference",
            "EB2": "Second Preference",
            "EB3": "Third Preference",
        }

        for cat_key, cat_label in categories.items():
            cat_header = _get_row_values(cat_label)
            if cat_header is not None:
                # "Total Petitions" is the next significant row
                tp_row = _get_row_values("Total Petitions", cat_header - header_row)
                ap_row = _get_row_values("Approved", cat_header - header_row)
                dn_row = _get_row_values("Denied", cat_header - header_row)
                pn_row = _get_row_values("Pending", cat_header - header_row)
                result[cat_key] = {}
                if tp_row is not None:
                    result[cat_key]["receipts"] = _extract_fy_values(tp_row)
                if ap_row is not None:
                    result[cat_key]["approved"] = _extract_fy_values(ap_row)
                if dn_row is not None:
                    result[cat_key]["denied"] = _extract_fy_values(dn_row)
                if pn_row is not None:
                    result[cat_key]["pending"] = _extract_fy_values(pn_row)

        return result

    def _detect_sheet(self, country_key: str) -> Optional[str]:
        """Find the sheet name matching a country key (case-insensitive partial match)."""
        xls = pd.ExcelFile(self.file_path)
        for sheet in xls.sheet_names:
            for pattern, key in _SHEET_COUNTRY_MAP.items():
                if key == country_key and pattern.lower() in sheet.lower():
                    return sheet
        return None

    def get_receipts_by_fy(self, country: str = "All") -> list[dict]:
        """Return annual I-140 receipt (new filing) totals by fiscal year.

        Returns list of dicts: [{fiscal_year, receipts, approved, denied, pending,
                                 eb1_receipts, eb2_receipts, eb3_receipts, approval_rate}]
        """
        sheet = self._detect_sheet(country)
        if sheet is None:
            return []
        data = self._parse_sheet(sheet)
        if not data or "overall" not in data:
            return []

        overall = data["overall"]
        receipts = overall.get("receipts", {})
        approved = overall.get("approved", {})
        denied = overall.get("denied", {})
        pending = overall.get("pending", {})

        result = []
        for fy in sorted(receipts.keys()):
            r = receipts.get(fy, 0)
            a = approved.get(fy, 0)
            d = denied.get(fy, 0)
            p = pending.get(fy, 0)

            entry = {
                "fiscal_year": fy,
                "receipts": r,
                "approved": a,
                "denied": d,
                "pending": p,
                "approval_rate": round(a / r * 100, 1) if r > 0 else 0,
                "eb1_receipts": data.get("EB1", {}).get("receipts", {}).get(fy, 0),
                "eb2_receipts": data.get("EB2", {}).get("receipts", {}).get(fy, 0),
                "eb3_receipts": data.get("EB3", {}).get("receipts", {}).get(fy, 0),
            }
            result.append(entry)
        return result

    def get_growth_rates(self, country: str = "All") -> list[dict]:
        """Return year-over-year growth rates for I-140 receipts.

        Returns: [{fiscal_year, receipts, yoy_growth_pct, eb1_growth_pct, eb2_growth_pct, eb3_growth_pct}]
        """
        by_fy = self.get_receipts_by_fy(country)
        result = []
        for i, row in enumerate(by_fy):
            entry = {
                "fiscal_year": row["fiscal_year"],
                "receipts": row["receipts"],
                "yoy_growth_pct": None,
                "eb1_growth_pct": None,
                "eb2_growth_pct": None,
                "eb3_growth_pct": None,
            }
            if i > 0:
                prev = by_fy[i - 1]
                if prev["receipts"] > 0:
                    entry["yoy_growth_pct"] = round(
                        (row["receipts"] - prev["receipts"]) / prev["receipts"] * 100, 1
                    )
                if prev["eb1_receipts"] > 0:
                    entry["eb1_growth_pct"] = round(
                        (row["eb1_receipts"] - prev["eb1_receipts"]) / prev["eb1_receipts"] * 100, 1
                    )
                if prev["eb2_receipts"] > 0:
                    entry["eb2_growth_pct"] = round(
                        (row["eb2_receipts"] - prev["eb2_receipts"]) / prev["eb2_receipts"] * 100, 1
                    )
                if prev["eb3_receipts"] > 0:
                    entry["eb3_growth_pct"] = round(
                        (row["eb3_receipts"] - prev["eb3_receipts"]) / prev["eb3_receipts"] * 100, 1
                    )
            result.append(entry)
        return result

    def get_country_comparison(self) -> list[dict]:
        """Return I-140 receipts comparison across all countries for the latest FY.

        Returns: [{country, receipts, eb1, eb2, eb3, share_pct}]
        """
        countries = ["All", "India", "China", "Philippines", "Brazil", "Vietnam"]
        all_data = {}
        for c in countries:
            by_fy = self.get_receipts_by_fy(c)
            if by_fy:
                all_data[c] = by_fy

        if "All" not in all_data:
            return []

        latest_fy = all_data["All"][-1]["fiscal_year"]
        all_total = all_data["All"][-1]["receipts"]

        result = []
        for c in countries:
            if c == "All" or c not in all_data:
                continue
            latest = next((r for r in all_data[c] if r["fiscal_year"] == latest_fy), None)
            if latest:
                result.append({
                    "country": c,
                    "receipts": latest["receipts"],
                    "eb1": latest["eb1_receipts"],
                    "eb2": latest["eb2_receipts"],
                    "eb3": latest["eb3_receipts"],
                    "share_pct": round(latest["receipts"] / all_total * 100, 1) if all_total > 0 else 0,
                })

        result.sort(key=lambda x: x["receipts"], reverse=True)
        return result

    def get_india_queue_growth(self) -> dict:
        """Return India-specific queue growth analysis.

        This is the key metric: how fast is India adding new I-140s to the system?
        """
        india_data = self.get_receipts_by_fy("India")
        all_data = self.get_receipts_by_fy("All")
        if not india_data or not all_data:
            return {}

        latest = india_data[-1]
        prev = india_data[-2] if len(india_data) > 1 else None
        all_latest = next((r for r in all_data if r["fiscal_year"] == latest["fiscal_year"]), None)

        # Compute average annual growth rate over last 5 years
        recent = india_data[-6:] if len(india_data) >= 6 else india_data
        if len(recent) >= 2:
            first_r, last_r = recent[0]["receipts"], recent[-1]["receipts"]
            years = recent[-1]["fiscal_year"] - recent[0]["fiscal_year"]
            if first_r > 0 and years > 0:
                cagr = ((last_r / first_r) ** (1 / years) - 1) * 100
            else:
                cagr = 0
        else:
            cagr = 0

        # Pending backlog (petitions filed but not yet resolved)
        total_pending = sum(r["pending"] for r in india_data)

        return {
            "latest_fy": latest["fiscal_year"],
            "latest_receipts": latest["receipts"],
            "latest_eb1": latest["eb1_receipts"],
            "latest_eb2": latest["eb2_receipts"],
            "latest_eb3": latest["eb3_receipts"],
            "yoy_growth_pct": round(
                (latest["receipts"] - prev["receipts"]) / prev["receipts"] * 100, 1
            ) if prev and prev["receipts"] > 0 else None,
            "india_share_pct": round(
                latest["receipts"] / all_latest["receipts"] * 100, 1
            ) if all_latest and all_latest["receipts"] > 0 else 0,
            "cagr_5yr_pct": round(cagr, 1),
            "total_pending_all_fy": total_pending,
            "approval_rate": latest["approval_rate"],
        }

    def get_summary(self) -> dict:
        """Return comprehensive summary for API response."""
        all_data = self.get_receipts_by_fy("All")
        india_data = self.get_receipts_by_fy("India")
        country_comp = self.get_country_comparison()
        india_growth = self.get_india_queue_growth()

        if not all_data:
            return {}

        latest = all_data[-1]
        fiscal_years = [r["fiscal_year"] for r in all_data]

        return {
            "fiscal_years": fiscal_years,
            "latest_fy": latest["fiscal_year"],
            "latest_total_receipts": latest["receipts"],
            "latest_total_approved": latest["approved"],
            "latest_total_pending": latest["pending"],
            "latest_approval_rate": latest["approval_rate"],
            "india_queue_growth": india_growth,
            "top_countries": country_comp[:5],
            "data_points": len(all_data),
            "source": "USCIS I-140 Receipts by Classification and Country",
        }
