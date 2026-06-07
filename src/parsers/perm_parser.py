"""Parser for DOL PERM Labor Certification Disclosure Data.

PERM (Program Electronic Review Management) Labor Certification is the first
step in the EB-2/EB-3 green card process. A certified PERM is a ~12-24 month
leading indicator of a future I-140 filing. By analyzing PERM certifications
by country and inferred EB category, we can model the "pipeline of future
demand" entering the employment-based immigration system.

Data source: DOL OFLC Performance Data
  https://www.dol.gov/agencies/eta/foreign-labor/performance
  Published quarterly as Excel files.

Files: data/DOL_PERM/PERM_Disclosure_Data_FY{YYYY}_Q{N}.xlsx
  - One row per PERM case with a final determination
  - Key columns: CASE_STATUS, COUNTRY_OF_CITIZENSHIP, DECISION_DATE,
    RECEIVED_DATE, MINIMUM_EDUCATION (or FOREIGN_WORKER_EDUCATION)

EB category inference from education requirement:
  - EB-2: Master's, Doctorate, Professional, or jobs requiring Bachelor's + 5yr exp
  - EB-3: Bachelor's, Associate's, None, High School, Other
  (This is an approximation — actual EB category is determined at I-140 stage)

Coverage: FY2023–FY2026 Q2
"""

import glob
import re
from pathlib import Path
from typing import Optional

import pandas as pd


__all__ = ["PERMParser"]

# Education levels that map to EB-2 (advanced degree or equivalent)
_EB2_EDUCATION = {
    "MASTER'S",
    "DOCTORATE",
    "PROFESSIONAL",
    "MASTER'S DEGREE",
    "DOCTORATE DEGREE",
    "PROFESSIONAL DEGREE",
    "DOCTORATE (PHD)",
}

# Education levels that map to EB-3 (bachelor's or below)
_EB3_EDUCATION = {
    "BACHELOR'S",
    "BACHELOR'S DEGREE",
    "ASSOCIATE'S",
    "ASSOCIATE'S DEGREE",
    "HIGH SCHOOL",
    "HIGH SCHOOL DIPLOMA",
    "NONE",
    "OTHER",
}

# Country name normalization for consistency with other parsers
_COUNTRY_ALIASES = {
    "INDIA": "India",
    "CHINA": "China",
    "CHINA, PEOPLES REPUBLIC OF": "China",
    "CHINA, PEOPLE'S REPUBLIC OF": "China",
    "SOUTH KOREA": "South Korea",
    "KOREA, SOUTH": "South Korea",
    "KOREA, REPUBLIC OF": "South Korea",
    "PHILIPPINES": "Philippines",
    "MEXICO": "Mexico",
    "CANADA": "Canada",
    "TAIWAN": "Taiwan",
    "BRAZIL": "Brazil",
    "PAKISTAN": "Pakistan",
    "UNITED KINGDOM": "United Kingdom",
    "JAPAN": "Japan",
    "NIGERIA": "Nigeria",
}


def _normalize_country(raw: str) -> str:
    """Normalize country name to canonical form used across project."""
    upper = str(raw).strip().upper()
    return _COUNTRY_ALIASES.get(upper, raw.strip().title())


def _infer_eb_category(education: str) -> str:
    """Infer EB-2 vs EB-3 from education requirement.

    Returns 'EB-2', 'EB-3', or 'Unknown'.
    """
    if pd.isna(education) or not education:
        return "Unknown"
    upper = str(education).strip().upper()
    if upper in _EB2_EDUCATION:
        return "EB-2"
    if upper in _EB3_EDUCATION:
        return "EB-3"
    return "Unknown"


def _parse_fy_from_filename(name: str) -> Optional[tuple[int, int]]:
    """Extract (fiscal_year, quarter) from PERM filename.

    e.g. 'PERM_Disclosure_Data_FY2025_Q4.xlsx' -> (2025, 4)
    """
    m = re.search(r"FY(\d{4})_Q(\d)", name, re.IGNORECASE)
    if m:
        return int(m.group(1)), int(m.group(2))
    m = re.search(r"FY(\d{4})", name, re.IGNORECASE)
    if m:
        return int(m.group(1)), 4  # Assume full year
    return None


class PERMParser:
    """Parser for DOL PERM Labor Certification disclosure data.

    Reads all PERM XLSX files from data/DOL_PERM/ and provides aggregated
    views suitable for modeling EB-2/EB-3 pipeline demand.
    """

    # Possible column names across FY versions (pre/post form revision)
    _STATUS_COLS = ["CASE_STATUS"]
    _COUNTRY_COLS = [
        "COUNTRY_OF_CITIZENSHIP",
        "COUNTRY_OF_CITZENSHIP",  # Known typo in older datasets
        "FOREIGN_WORKER_BIRTH_COUNTRY",
        "COUNTRY_OF_BIRTH",
    ]
    _EDUCATION_COLS = [
        "MINIMUM_EDUCATION",
        "FOREIGN_WORKER_EDUCATION",
        "EDUCATION_LEVEL_REQUIRED",
    ]
    _DECISION_DATE_COLS = ["DECISION_DATE"]
    _RECEIVED_DATE_COLS = ["RECEIVED_DATE", "CASE_RECEIVED_DATE"]
    _EMPLOYER_COLS = ["EMPLOYER_NAME", "EMP_BUSINESS_NAME"]
    _SOC_TITLE_COLS = ["PW_SOC_TITLE", "PWD_SOC_TITLE", "SOC_TITLE", "JOB_TITLE"]
    _WAGE_COLS = ["WAGE_OFFER_FROM_1", "WAGE_OFFER_FROM", "JOB_OPP_WAGE_FROM", "PW_WAGE_1", "PW_WAGE"]

    def __init__(self, data_dir: str = "data/DOL_PERM"):
        self.data_dir = Path(data_dir)
        self._cache: Optional[pd.DataFrame] = None

    def _find_column(self, df: pd.DataFrame, candidates: list[str]) -> Optional[str]:
        """Find the first matching column name from candidates (case-insensitive)."""
        upper_cols = {c.upper(): c for c in df.columns}
        for cand in candidates:
            if cand.upper() in upper_cols:
                return upper_cols[cand.upper()]
        return None

    def _load_single_file(self, filepath: Path) -> Optional[pd.DataFrame]:
        """Load and normalize a single PERM disclosure file."""
        try:
            df = pd.read_excel(filepath, dtype=str)
        except Exception:
            return None

        if df.empty:
            return None

        # Strip whitespace from column names
        df.columns = [str(c).strip() for c in df.columns]

        # Find and rename key columns to canonical names
        col_map = {}
        status_col = self._find_column(df, self._STATUS_COLS)
        country_col = self._find_column(df, self._COUNTRY_COLS)
        edu_col = self._find_column(df, self._EDUCATION_COLS)
        decision_col = self._find_column(df, self._DECISION_DATE_COLS)
        received_col = self._find_column(df, self._RECEIVED_DATE_COLS)
        soc_col = self._find_column(df, self._SOC_TITLE_COLS)
        employer_col = self._find_column(df, self._EMPLOYER_COLS)

        if status_col:
            col_map[status_col] = "case_status"
        if country_col:
            col_map[country_col] = "country"
        if edu_col:
            col_map[edu_col] = "education"
        if decision_col:
            col_map[decision_col] = "decision_date"
        if received_col:
            col_map[received_col] = "received_date"
        if soc_col:
            col_map[soc_col] = "soc_title"
        if employer_col:
            col_map[employer_col] = "employer"

        df = df.rename(columns=col_map)

        # Add fiscal year from filename
        fy_info = _parse_fy_from_filename(filepath.name)
        if fy_info:
            df["fiscal_year"] = fy_info[0]
            df["quarter"] = fy_info[1]
        else:
            df["fiscal_year"] = 0
            df["quarter"] = 0

        df["source_file"] = filepath.name

        # Normalize country names
        if "country" in df.columns:
            df["country"] = df["country"].apply(
                lambda x: _normalize_country(x) if pd.notna(x) else "Unknown"
            )

        # Infer EB category from education
        if "education" in df.columns:
            df["inferred_eb"] = df["education"].apply(_infer_eb_category)
        else:
            df["inferred_eb"] = "Unknown"

        # Parse dates
        for date_col in ["decision_date", "received_date"]:
            if date_col in df.columns:
                df[date_col] = pd.to_datetime(df[date_col], errors="coerce")

        # Keep only relevant columns that exist
        keep = [
            "case_status", "country", "education", "inferred_eb",
            "decision_date", "received_date", "soc_title", "employer",
            "fiscal_year", "quarter", "source_file",
        ]
        keep = [c for c in keep if c in df.columns]
        return df[keep]

    def _load_all(self) -> pd.DataFrame:
        """Load and concatenate all PERM files from data directory."""
        if self._cache is not None:
            return self._cache

        # Glob both standard and "New Form" files
        pattern1 = str(self.data_dir / "PERM_Disclosure_Data*.xlsx")
        pattern2 = str(self.data_dir / "PERM_Disclosure_Data_New_Form*.xlsx")
        files = sorted(set(glob.glob(pattern1)) | set(glob.glob(pattern2)))
        if not files:
            pattern = str(self.data_dir / "perm*.xlsx")
            files = sorted(glob.glob(pattern))

        if not files:
            self._cache = pd.DataFrame()
            return self._cache

        frames = []
        for f in files:
            df = self._load_single_file(Path(f))
            if df is not None and not df.empty:
                frames.append(df)

        if not frames:
            self._cache = pd.DataFrame()
            return self._cache

        self._cache = pd.concat(frames, ignore_index=True)

        # After concatenation, fill NaN values from files that lack certain columns
        # (FY2025+ new form doesn't include country/education in disclosure data)
        if "country" in self._cache.columns:
            self._cache["country"] = self._cache["country"].fillna("Unknown")
        if "inferred_eb" in self._cache.columns:
            self._cache["inferred_eb"] = self._cache["inferred_eb"].fillna("Unknown")

        return self._cache

    def _certified(self) -> pd.DataFrame:
        """Return only certified cases."""
        df = self._load_all()
        if df.empty or "case_status" not in df.columns:
            return pd.DataFrame()
        return df[df["case_status"].str.upper().str.strip() == "CERTIFIED"]

    # ──────────────────────────────────────────────
    # Public API
    # ──────────────────────────────────────────────

    def get_certified_by_fy(self) -> list[dict]:
        """Certified PERM counts by fiscal year, broken down by country group.

        For FYs without country data (FY2025+ new form), india/china will be 0
        and has_country_data will be false.

        Returns list of dicts:
          [{"fiscal_year": 2025, "total": 150000, "india": 80000, "china": 15000, "row": 55000, "has_country_data": true}, ...]
        """
        cert = self._certified()
        if cert.empty:
            return []

        results = []
        for fy, group in cert.groupby("fiscal_year"):
            if fy == 0:
                continue
            india = int((group["country"] == "India").sum())
            china = int((group["country"] == "China").sum())
            unknown = int((group["country"] == "Unknown").sum())
            total = len(group)
            has_country = unknown < total * 0.5  # More than half have known countries
            results.append({
                "fiscal_year": int(fy),
                "total": total,
                "india": india,
                "china": china,
                "row": total - india - china - unknown,
                "has_country_data": has_country,
            })

        results.sort(key=lambda x: x["fiscal_year"])
        return results

    def get_certified_by_category(self) -> list[dict]:
        """Certified PERM counts by fiscal year and inferred EB category.

        Returns list of dicts:
          [{"fiscal_year": 2025, "eb2": 90000, "eb3": 50000, "unknown": 10000}, ...]
        """
        cert = self._certified()
        if cert.empty:
            return []

        results = []
        for fy, group in cert.groupby("fiscal_year"):
            if fy == 0:
                continue
            eb2 = int((group["inferred_eb"] == "EB-2").sum())
            eb3 = int((group["inferred_eb"] == "EB-3").sum())
            unknown = int((group["inferred_eb"] == "Unknown").sum())
            results.append({
                "fiscal_year": int(fy),
                "eb2": eb2,
                "eb3": eb3,
                "unknown": unknown,
                "total": eb2 + eb3 + unknown,
            })

        results.sort(key=lambda x: x["fiscal_year"])
        return results

    def get_india_pipeline(self) -> list[dict]:
        """India-specific certified PERMs by FY and inferred EB category.

        This is the key "future demand" indicator: each certified India PERM
        will likely become an India EB-2 or EB-3 I-140 within 12-24 months.

        Only includes FYs where country data is available (FY2023-FY2024 with
        old ETA-9089 form). FY2025+ lacks country attribution in disclosure data.

        Returns list of dicts:
          [{"fiscal_year": 2024, "eb2": 8065, "eb3": 8047, "total": 16173}, ...]
        """
        cert = self._certified()
        if cert.empty:
            return []

        india = cert[cert["country"] == "India"]
        results = []
        for fy, group in india.groupby("fiscal_year"):
            if fy == 0:
                continue
            total = len(group)
            if total == 0:
                continue  # Skip FYs with no India data
            eb2 = int((group["inferred_eb"] == "EB-2").sum())
            eb3 = int((group["inferred_eb"] == "EB-3").sum())
            unknown = int((group["inferred_eb"] == "Unknown").sum())
            results.append({
                "fiscal_year": int(fy),
                "eb2": eb2,
                "eb3": eb3,
                "unknown": unknown,
                "total": total,
            })

        results.sort(key=lambda x: x["fiscal_year"])
        return results

    def get_top_countries(self, top_n: int = 10) -> list[dict]:
        """Top countries by total certified PERMs (excludes Unknown/unavailable).

        Only reflects FYs where country data is available in the disclosure files.

        Returns list of dicts:
          [{"country": "India", "total": 300000, "pct": 55.2}, ...]
        """
        cert = self._certified()
        if cert.empty:
            return []

        # Exclude "Unknown" (from FYs where country data is unavailable)
        known = cert[cert["country"] != "Unknown"]
        if known.empty:
            return []

        counts = known["country"].value_counts().head(top_n)
        grand_total = len(known)
        results = []
        for country, count in counts.items():
            results.append({
                "country": str(country),
                "total": int(count),
                "pct": round(count / grand_total * 100, 1),
            })
        return results

    def get_status_breakdown(self) -> list[dict]:
        """Case status breakdown by fiscal year.

        Statuses: Certified (active), Certified-Expired (certified but I-140
        not filed in time), Denied, Withdrawn.

        Returns list of dicts per FY with counts and approval rate.
        """
        df = self._load_all()
        if df.empty:
            return []

        results = []
        for fy, group in df.groupby("fiscal_year"):
            if fy == 0:
                continue
            status = group["case_status"].str.upper().str.strip()
            certified = int((status == "CERTIFIED").sum())
            # "CERTIFIED-EXPIRED" and "CERTIFIED - EXPIRED" are PERMs that were
            # certified but expired before the I-140 was filed (180-day validity)
            cert_expired = int(status.str.contains("CERTIFIED.*EXPIRED", regex=True).sum())
            denied = int((status == "DENIED").sum())
            withdrawn = int((status == "WITHDRAWN").sum())
            other = len(group) - certified - cert_expired - denied - withdrawn
            total_determined = len(group)
            # Approval rate: both active and expired certs count as "approved by DOL"
            total_certified = certified + cert_expired
            results.append({
                "fiscal_year": int(fy),
                "certified": certified,
                "certified_expired": cert_expired,
                "denied": denied,
                "withdrawn": withdrawn,
                "other": other,
                "total": total_determined,
                "approval_rate": round(total_certified / total_determined * 100, 1) if total_determined > 0 else 0,
            })

        results.sort(key=lambda x: x["fiscal_year"])
        return results

    def get_summary(self) -> dict:
        """High-level summary across all loaded data.

        Returns dict with total counts, India pipeline estimate, and coverage info.
        """
        df = self._load_all()
        if df.empty:
            return {
                "error": "No PERM data available",
                "total_cases": 0,
                "fiscal_years": [],
            }

        cert = self._certified()
        india_cert = cert[cert["country"] == "India"] if not cert.empty else pd.DataFrame()

        fiscal_years = sorted([int(fy) for fy in df["fiscal_year"].unique() if fy != 0])

        # Latest FY stats for India (use latest FY that has country data)
        india_latest = {}
        india_by_fy = self.get_india_pipeline()
        if india_by_fy:
            latest = india_by_fy[-1]
            india_latest = {
                "fiscal_year": latest["fiscal_year"],
                "total": latest["total"],
                "eb2": latest["eb2"],
                "eb3": latest["eb3"],
            }

        # Compute YoY growth for India certified PERMs
        yoy_growth = None
        if len(india_by_fy) >= 2:
            prev = india_by_fy[-2]["total"]
            curr = india_by_fy[-1]["total"]
            if prev > 0:
                yoy_growth = round((curr - prev) / prev * 100, 1)

        # Determine which FYs have country/education data
        fys_with_country = []
        fys_without_country = []
        for fy in fiscal_years:
            fy_data = cert[cert["fiscal_year"] == fy] if not cert.empty else pd.DataFrame()
            if not fy_data.empty and "country" in fy_data.columns:
                known = fy_data[fy_data["country"] != "Unknown"]
                if len(known) > len(fy_data) * 0.1:
                    fys_with_country.append(fy)
                else:
                    fys_without_country.append(fy)
            else:
                fys_without_country.append(fy)

        return {
            "total_cases": len(df),
            "total_certified": len(cert),
            "total_india_certified": len(india_cert),
            "fiscal_years": fiscal_years,
            "latest_fy": fiscal_years[-1] if fiscal_years else None,
            "india_latest": india_latest,
            "india_yoy_growth_pct": yoy_growth,
            "data_points": len(fiscal_years),
            "fys_with_country_data": fys_with_country,
            "fys_without_country_data": fys_without_country,
            "source": "DOL OFLC PERM Disclosure Data",
            "note": "FY2025+ uses new ETA-9089 form; worker demographics (country, education) moved to Appendix A and are not in disclosure data. Country/category breakdowns available for FY2023-FY2024 only.",
        }
