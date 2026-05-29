import os

import pandas as pd
import numpy as np
from typing import Any, List, Optional

from ..constants import DEPENDENT_MULTIPLIER


class ParserUtils:
    """Static utility methods extracted from BaseParser for independent testing.

    All methods are pure functions operating on DataFrames / values —
    no instance state required.
    """

    # Common variations of the chargeability header
    CHARGEABILITY_HEADERS = [
        "Foreign State of Chargeability",
        "Place of Birth",
        "Country",
        "Foreign State",
    ]

    @staticmethod
    def normalize_headers(df: pd.DataFrame, chargeability_headers: List[str] = None) -> pd.DataFrame:
        """Standardizes common headers to a single canonical name.

        Returns a new DataFrame with normalized column names.
        """
        if chargeability_headers is None:
            chargeability_headers = ParserUtils.CHARGEABILITY_HEADERS

        new_cols = []
        found_chargeability = False

        for col in df.columns:
            col_str = str(col).strip()
            if not found_chargeability and any(
                h.lower() == col_str.lower() or h.lower() in col_str.lower()
                for h in chargeability_headers
            ):
                new_cols.append("chargeability")
                found_chargeability = True
            else:
                new_cols.append(col_str.lower().replace(" ", "_").replace("-", "_"))

        result = df.copy()
        result.columns = new_cols

        # Strip values in 'chargeability' if it exists
        if "chargeability" in result.columns:
            result["chargeability"] = result["chargeability"].apply(
                lambda x: str(x).strip() if pd.notna(x) else x
            )
            # Filter out rows where chargeability is the same as the header name (leaked row)
            result = result[
                ~result["chargeability"].str.contains(
                    "Foreign State of Chargeability", case=False, na=False
                )
            ]

        return result

    @staticmethod
    def normalize_disclosure_values(df: pd.DataFrame, columns: List[str]) -> pd.DataFrame:
        """Converts 'D' (Disclosure) values to 1 and ensures numeric columns.

        Returns a new DataFrame with normalized values.
        """
        def _handle_val(val):
            s_val = str(val).strip().upper()
            if s_val == "D":
                return 1
            if s_val.startswith("<"):
                try:
                    return int(s_val[1:]) // 2
                except ValueError:
                    return 1
            return val

        result = df.copy()

        for col in columns:
            if col in result.columns:
                result[col] = result[col].apply(_handle_val)
                result[col] = pd.to_numeric(result[col], errors="coerce").fillna(0).astype(int)

        return result

    @staticmethod
    def find_header_row(file_path: str, keywords: List[str], max_rows: int = 15, sheet_name: Optional[Any] = 0) -> int:
        """Scans the first few rows to find the one containing most keywords.

        Returns the row index where the header was found, or 0 if not found.
        """
        temp_df = pd.read_excel(file_path, header=None, nrows=max_rows, sheet_name=sheet_name)
        if isinstance(temp_df, dict):
            temp_df = list(temp_df.values())[0]

        for i, row in temp_df.iterrows():
            row_str = " ".join(str(val).lower() for val in row.values)
            if all(k.lower() in row_str for k in keywords):
                return i
        return 0


class BaseParser:
    """
    Base class for parsing government CSV and Excel data.
    Handles common issues like 'D' disclosure strings and header normalization.
    """

    # Dependent multiplier (primary + 2.2x dependents) per project mandate
    DEPENDENT_MULTIPLIER = DEPENDENT_MULTIPLIER

    # Canonical list lives in ParserUtils; alias here for backward compat
    CHARGEABILITY_HEADERS = ParserUtils.CHARGEABILITY_HEADERS

    def __init__(self, file_path: str):
        self.file_path = file_path
        self.df: Optional[pd.DataFrame] = None

    def load_data(self, sheet_name: Optional[str] = None, prevent_recursion: bool = False, **kwargs) -> pd.DataFrame:
        """Loads the data based on file extension."""
        if not os.path.exists(self.file_path):
            raise FileNotFoundError(f"Data file not found: {self.file_path}")

        if self.file_path.endswith('.csv'):
            self.df = pd.read_csv(self.file_path, **kwargs)
        elif self.file_path.endswith(('.xlsx', '.xls')):
            if sheet_name:
                self.df = pd.read_excel(self.file_path, sheet_name=sheet_name, **kwargs)
            else:
                self.df = pd.read_excel(self.file_path, **kwargs)
        else:
            raise ValueError(f"Unsupported file format: {self.file_path}")
        return self.df

    def find_header_row(self, keywords: List[str], max_rows: int = 15, sheet_name: Optional[Any] = 0) -> int:
        """
        Scans the first few rows to find the one containing most keywords.
        Updates self.df if found.

        Delegates the row-search logic to ParserUtils.find_header_row(), then
        reloads data with the correct header offset.
        """
        header_idx = ParserUtils.find_header_row(
            self.file_path, keywords, max_rows=max_rows, sheet_name=sheet_name
        )
        if header_idx > 0:
            # Reload with the correct header, using prevent_recursion to avoid infinite loops in subclasses
            self.load_data(header=header_idx, sheet_name=sheet_name, prevent_recursion=True)
        return header_idx

    def normalize_headers(self):
        """Standardizes common headers to a single canonical name.

        Delegates to ParserUtils and updates self.df in-place for backward compat.
        """
        if self.df is None:
            return
        self.df = ParserUtils.normalize_headers(self.df, self.CHARGEABILITY_HEADERS)

    def normalize_disclosure_values(self, columns: List[str]):
        """Converts 'D' (Disclosure) values to 1 and ensures the column is numeric.

        Delegates to ParserUtils and updates self.df in-place for backward compat.
        """
        if self.df is None:
            return
        self.df = ParserUtils.normalize_disclosure_values(self.df, columns)

    def clean(self):
        """Main entry point for cleaning. To be overridden by subclasses."""
        self.normalize_headers()

    def parse(self) -> pd.DataFrame:
        """Parse the underlying data source and return a DataFrame.

        Satisfies the Parser protocol from src.domain.protocols.
        Subclasses may override for custom load+clean logic.
        """
        self.load_data()
        self.clean()
        return self.df
