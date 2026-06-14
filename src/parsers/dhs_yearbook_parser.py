"""Parser for DHS Yearbook of Immigration Statistics — Table 7.

Extracts employment-based (EB) immigration principal/derivative counts and
computes dependent multipliers by preference category (EB1–EB5).

Data sources:
- DHS Yearbook of Immigration Statistics, Table 7:
  "Persons Obtaining Lawful Permanent Resident Status by Type and Detailed
  Class of Admission"
  https://ohss.dhs.gov/topics/immigration/yearbook/{year}/table7

- Raw Excel workbooks (FY2022–FY2024):
  data/DHS_Yearbook/dhs_yearbook_lpr_fy2024.xlsx (sheet "Table 7")
  data/DHS_Yearbook/dhs_yearbook_lpr_fy2023.xlsx (sheet "Table 7")
  data/DHS_Yearbook/dhs_yearbook_lpr_fy2022.xlsx (sheet "Table 7d")

- Pre-extracted CSV (FY2015–FY2024):
  data/DHS_Yearbook/dhs_table7_eb_multipliers.csv

The multiplier = total_persons / principals for each EB category.  It converts
I-140 pipeline counts (principal-only) into total visa demand (including
spouses and children).  Each EB category has a structurally different
derivative rate (e.g., EB-1 ~2.5x, EB-2 ~2.0x).

Key exclusions for EB-4:
- SL6 (juvenile court dependents — no I-140 petition, no derivatives)
- SI/SQ/SU/SW (Iraqi/Afghan SIVs — listed separately in Table 7)
"""

from pathlib import Path
from typing import Optional

import pandas as pd


# ── Visa code mapping for DHS Table 7 EB categories ──────────────────────────
# Each category maps to principal, spouse, and child visa symbol codes.
# Used by the download script to aggregate raw Table 7 rows into EB1–EB5.

EB_VISA_CODES: dict[str, dict[str, list[str]]] = {
    "EB1": {
        "principal_codes": ["E11", "E16", "E12", "E17", "E13", "E18"],
        "spouse_codes": ["E14", "E19"],
        "child_codes": ["E15", "E10"],
    },
    "EB2": {
        "principal_codes": ["E21", "E26"],
        "spouse_codes": ["E22", "E27"],
        "child_codes": ["E23", "E28"],
    },
    "EB3": {
        "principal_codes": ["E31", "E36", "E32", "E37", "EW3", "EW8"],
        "spouse_codes": ["E34", "E39", "EW4", "EW9", "EX7"],
        "child_codes": ["E35", "E30", "EW5", "EW0"],
    },
    "EB4": {
        "principal_codes": [
            "BC1", "BC6", "SD1", "SD6", "SE1", "SE6",
            "SG1", "SG6", "SH6", "SK6", "SN6", "SR1", "SR6",
        ],
        "spouse_codes": [
            "BC2", "BC7", "SD2", "SD7", "SE2", "SE7", "SG2",
            "SK7", "SN7", "SR2", "SR7",
        ],
        "child_codes": [
            "BC3", "BC8", "SD3", "SD8", "SE3", "SE8",
            "SK8", "SN8", "SR3", "SR8",
        ],
    },
    "EB5": {
        "principal_codes": [
            "C51", "C56", "E56", "I51", "I56", "T51", "T56", "R51", "R56",
        ],
        "spouse_codes": [
            "C52", "C57", "E57", "I52", "I57", "T52", "T57", "R52", "R57",
        ],
        "child_codes": [
            "C53", "C58", "E53", "I53", "I58", "T53", "T58", "R53", "R58",
        ],
    },
}

# Hardcoded fallback when no data files are available (matches project constants)
_FALLBACK_MULTIPLIERS: dict[str, float] = {
    "EB1": 2.5,
    "EB2": 2.0,
    "EB3": 2.1,
    "EB4": 2.35,
    "EB5": 2.55,
}

_EB_CATEGORIES: list[str] = ["EB1", "EB2", "EB3", "EB4", "EB5"]

_CSV_FILENAME = "dhs_table7_eb_multipliers.csv"


class DhsYearbookParser:
    """Parser for DHS Yearbook Table 7 dependent multiplier data.

    Primary data source is the pre-extracted CSV.  Falls back to parsing
    the raw Excel workbooks, and ultimately to hardcoded constants if no
    data files are available.
    """

    def __init__(self, data_dir: str = "data/DHS_Yearbook") -> None:
        """Initialize the parser.

        Args:
            data_dir: Directory containing the DHS Yearbook data files.
        """
        self._data_dir = Path(data_dir)
        self._df: Optional[pd.DataFrame] = None

    # ── Data loading ──────────────────────────────────────────────────────────

    def _load(self) -> pd.DataFrame:
        """Load multiplier data, trying CSV first, then Excel, then fallback."""
        if self._df is not None:
            return self._df

        csv_path = self._data_dir / _CSV_FILENAME
        if csv_path.exists():
            self._df = pd.read_csv(csv_path)
            return self._df

        # Fall back to parsing Excel workbooks directly
        df = self._parse_excel_files()
        if df is not None and not df.empty:
            self._df = df
            return self._df

        # Final fallback: build a single-row DataFrame from hardcoded values
        self._df = self._build_fallback_df()
        return self._df

    def _parse_excel_files(self) -> Optional[pd.DataFrame]:
        """Attempt to parse raw Excel workbooks for FY2022/FY2023 data."""
        frames: list[pd.DataFrame] = []

        # FY2023 workbook (sheet "Table 7")
        fy2023_path = self._data_dir / "dhs_yearbook_lpr_fy2023.xlsx"
        if fy2023_path.exists():
            df = self._parse_single_excel(fy2023_path, "Table 7", 2023)
            if df is not None:
                frames.append(df)

        # FY2022 workbook (sheet "Table 7d")
        fy2022_path = self._data_dir / "dhs_yearbook_lpr_fy2022.xlsx"
        if fy2022_path.exists():
            df = self._parse_single_excel(fy2022_path, "Table 7d", 2022)
            if df is not None:
                frames.append(df)

        if not frames:
            return None
        return pd.concat(frames, ignore_index=True)

    @staticmethod
    def _parse_single_excel(
        path: Path, sheet_name: str, fiscal_year: int
    ) -> Optional[pd.DataFrame]:
        """Parse a single DHS Yearbook Excel workbook into multiplier rows.

        Reads the raw Table 7 sheet and aggregates visa codes into EB
        categories using EB_VISA_CODES.
        """
        try:
            raw = pd.read_excel(path, sheet_name=sheet_name, header=None)
        except Exception:
            return None

        # Find header row containing "Class of Admission" or similar
        header_row = 0
        for i, row in raw.head(20).iterrows():
            row_str = " ".join(str(v).lower() for v in row.values)
            if "class" in row_str and "admission" in row_str:
                header_row = i
                break

        raw.columns = raw.iloc[header_row]
        raw = raw.iloc[header_row + 1:].reset_index(drop=True)

        # Find the class-of-admission column
        class_col = None
        total_col = None
        for c in raw.columns:
            cs = str(c).lower()
            if "class" in cs and "admission" in cs:
                class_col = c
            if cs == "total":
                total_col = c

        if class_col is None:
            return None

        raw[class_col] = raw[class_col].astype(str).str.strip()

        rows: list[dict] = []
        for cat, codes in EB_VISA_CODES.items():
            all_codes = (
                codes["principal_codes"]
                + codes["spouse_codes"]
                + codes["child_codes"]
            )
            cat_rows = raw[raw[class_col].isin(all_codes)]

            def _sum_codes(code_list: list[str]) -> int:
                subset = raw[raw[class_col].isin(code_list)]
                if total_col and total_col in subset.columns:
                    return int(
                        pd.to_numeric(subset[total_col], errors="coerce")
                        .fillna(0)
                        .sum()
                    )
                return 0

            principals = _sum_codes(codes["principal_codes"])
            spouses = _sum_codes(codes["spouse_codes"])
            children = _sum_codes(codes["child_codes"])
            derivatives = spouses + children
            total = principals + derivatives
            multiplier = round(total / principals, 3) if principals > 0 else 0.0

            summary_total = 0
            if total_col and total_col in cat_rows.columns:
                summary_total = int(
                    pd.to_numeric(cat_rows[total_col], errors="coerce")
                    .fillna(0)
                    .sum()
                )

            rows.append({
                "fiscal_year": fiscal_year,
                "category": cat,
                "summary_total": summary_total,
                "principals": principals,
                "spouses": spouses,
                "children": children,
                "derivatives": derivatives,
                "total": total,
                "multiplier": multiplier,
            })

        return pd.DataFrame(rows)

    @staticmethod
    def _build_fallback_df() -> pd.DataFrame:
        """Build a minimal DataFrame from hardcoded fallback multipliers."""
        rows = []
        for cat, mult in _FALLBACK_MULTIPLIERS.items():
            rows.append({
                "fiscal_year": 0,
                "category": cat,
                "summary_total": 0,
                "principals": 0,
                "spouses": 0,
                "children": 0,
                "derivatives": 0,
                "total": 0,
                "multiplier": mult,
            })
        return pd.DataFrame(rows)

    # ── Public API ────────────────────────────────────────────────────────────

    def get_multipliers(self, fiscal_year: Optional[int] = None) -> dict[str, float]:
        """Return dependent multipliers by EB category for a given fiscal year.

        Args:
            fiscal_year: e.g. 2023.  If None, uses the latest available year.

        Returns:
            Dict like ``{"EB1": 2.497, "EB2": 2.010, ...}``.
        """
        df = self._load()
        if fiscal_year is None:
            fiscal_year = int(df["fiscal_year"].max())
        fy_df = df[df["fiscal_year"] == fiscal_year]
        if fy_df.empty:
            return dict(_FALLBACK_MULTIPLIERS)
        return {
            row["category"]: round(float(row["multiplier"]), 3)
            for _, row in fy_df.iterrows()
            if row["category"] in _EB_CATEGORIES
        }

    def get_latest_multipliers(self) -> dict[str, float]:
        """Return dependent multipliers for the most recent fiscal year.

        Convenience wrapper around :meth:`get_multipliers` with no year argument.
        """
        return self.get_multipliers(fiscal_year=None)

    def get_historical_multipliers(self) -> dict[int, dict[str, float]]:
        """Return multipliers for every available fiscal year.

        Returns:
            Nested dict ``{2023: {"EB1": 2.497, ...}, 2022: {...}, ...}``.
        """
        df = self._load()
        years = sorted(df["fiscal_year"].unique(), reverse=True)
        return {int(y): self.get_multipliers(int(y)) for y in years}

    def get_average_multipliers(self, last_n_years: int = 5) -> dict[str, float]:
        """Return average multipliers over the last N fiscal years.

        Args:
            last_n_years: Number of most-recent years to average.  Defaults to 5.

        Returns:
            Dict like ``{"EB1": 2.45, "EB2": 1.99, ...}``.
        """
        df = self._load()
        years = sorted(df["fiscal_year"].unique(), reverse=True)[:last_n_years]
        subset = df[df["fiscal_year"].isin(years)]
        result: dict[str, float] = {}
        for cat in _EB_CATEGORIES:
            cat_df = subset[subset["category"] == cat]
            if cat_df.empty:
                result[cat] = _FALLBACK_MULTIPLIERS.get(cat, 2.5)
            else:
                result[cat] = round(float(cat_df["multiplier"].mean()), 3)
        return result

    def get_category_detail(self, category: str) -> list[dict]:
        """Return per-year detail rows for a single EB category.

        Args:
            category: One of ``"EB1"`` through ``"EB5"``.

        Returns:
            List of dicts, each with keys: ``fiscal_year``, ``principals``,
            ``spouses``, ``children``, ``derivatives``, ``total``, ``multiplier``.
        """
        category = category.upper()
        df = self._load()
        cat_df = df[df["category"] == category].sort_values("fiscal_year")
        result: list[dict] = []
        for _, row in cat_df.iterrows():
            result.append({
                "fiscal_year": int(row["fiscal_year"]),
                "principals": int(row["principals"]),
                "spouses": int(row["spouses"]),
                "children": int(row["children"]),
                "derivatives": int(row["derivatives"]),
                "total": int(row["total"]),
                "multiplier": round(float(row["multiplier"]), 3),
            })
        return result

    def get_all_data(self) -> pd.DataFrame:
        """Return the full underlying DataFrame.

        Returns:
            DataFrame with columns: ``fiscal_year``, ``category``,
            ``summary_total``, ``principals``, ``spouses``, ``children``,
            ``derivatives``, ``total``, ``multiplier``.
        """
        return self._load().copy()

    def get_summary(self) -> dict:
        """Return a comprehensive summary of the DHS Yearbook multiplier data.

        Returns:
            Dict with keys: ``available_years``, ``latest_year``,
            ``latest_multipliers``, ``average_multipliers_5yr``,
            ``data_source``, ``notes``.
        """
        df = self._load()
        years = sorted(int(y) for y in df["fiscal_year"].unique())
        latest_year = years[-1] if years else 0

        return {
            "available_years": years,
            "latest_year": latest_year,
            "latest_multipliers": self.get_latest_multipliers(),
            "average_multipliers_5yr": self.get_average_multipliers(5),
            "data_source": str(self._data_dir / _CSV_FILENAME),
            "notes": {
                "definition": "multiplier = total_persons / principals",
                "scope": "Employment-based LPR admissions (EB1–EB5)",
                "eb4_exclusions": (
                    "SL6 (juvenile court dependents) and SI/SQ/SU/SW "
                    "(Iraqi/Afghan SIVs) are excluded"
                ),
                "source": "DHS Yearbook of Immigration Statistics, Table 7",
            },
        }


__all__ = [
    "DhsYearbookParser",
    "EB_VISA_CODES",
]