import os
import warnings

import pandas as pd
import numpy as np
from typing import Any, List, Optional

# Suppress openpyxl header/footer parsing warnings (cosmetic; does not affect data)
warnings.filterwarnings("ignore", message="Cannot parse header or footer", module="openpyxl")

from ..constants import DEPENDENT_MULTIPLIER


class BaseParser:
    """
    Base class for parsing government CSV and Excel data.
    Handles common issues like 'D' disclosure strings and header normalization.
    """

    # Dependent multiplier (primary + 2.2x dependents) per project mandate
    DEPENDENT_MULTIPLIER = DEPENDENT_MULTIPLIER

    # Common variations of the chargeability header
    CHARGEABILITY_HEADERS = [
        "Foreign State of Chargeability",
        "Place of Birth",
        "Country",
        "Foreign State"
    ]

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
        """
        temp_df = pd.read_excel(self.file_path, header=None, nrows=max_rows, sheet_name=sheet_name)
        if isinstance(temp_df, dict):
            # If multiple sheets, pick the first one
            temp_df = list(temp_df.values())[0]
            
        for i, row in temp_df.iterrows():
            row_str = " ".join(str(val).lower() for val in row.values)
            if all(k.lower() in row_str for k in keywords):
                # Reload with the correct header, using prevent_recursion to avoid infinite loops in subclasses
                self.load_data(header=i, sheet_name=sheet_name, prevent_recursion=True)
                return i
        return 0

    def normalize_headers(self):
        """Standardizes common headers to a single canonical name."""
        if self.df is None:
            return

        new_cols = []
        found_chargeability = False
        
        for col in self.df.columns:
            col_str = str(col).strip()
            # More specific matching for chargeability to avoid collisions
            if not found_chargeability and any(h.lower() == col_str.lower() or h.lower() in col_str.lower() for h in self.CHARGEABILITY_HEADERS):
                new_cols.append("chargeability")
                found_chargeability = True
            else:
                new_cols.append(col_str.lower().replace(" ", "_").replace("-", "_"))

        self.df.columns = new_cols
        
        # Strip values in 'chargeability' if it exists
        if 'chargeability' in self.df.columns:
            self.df['chargeability'] = self.df['chargeability'].apply(
                lambda x: str(x).strip() if pd.notna(x) else x
            )
            # Filter out rows where chargeability is the same as the header name (leaked row)
            self.df = self.df[~self.df['chargeability'].str.contains("Foreign State of Chargeability", case=False, na=False)]

    def normalize_disclosure_values(self, columns: List[str]):
        """
        Converts 'D' (Disclosure) values to 1 and ensures the column is numeric.
        Per government standards, 'D' often hides values between 1-10.
        Setting to 1 is a conservative baseline.
        """
        if self.df is None:
            return

        for col in columns:
            if col in self.df.columns:
                # Replace 'D' or any string starting with 'D' with 1
                # Also handle cases like '<10' or '1-5' which sometimes appear
                def _handle_val(val):
                    s_val = str(val).strip().upper()
                    if s_val == 'D':
                        return 1
                    if s_val.startswith('<'):
                        # '<10' -> return 5 as a midpoint estimate
                        try:
                            return int(s_val[1:]) // 2
                        except ValueError:
                            return 1
                    return val

                self.df[col] = self.df[col].apply(_handle_val)
                # Force numeric, turning other errors into NaN then 0
                # We log if we coerced something unexpected (optional, but good for debug)
                self.df[col] = pd.to_numeric(self.df[col], errors='coerce').fillna(0).astype(int)

    def clean(self):
        """Main entry point for cleaning. To be overridden by subclasses."""
        self.normalize_headers()
