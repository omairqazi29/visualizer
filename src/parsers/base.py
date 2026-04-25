import pandas as pd
import numpy as np
from typing import List, Optional

class BaseParser:
    """
    Base class for parsing government CSV and Excel data.
    Handles common issues like 'D' disclosure strings and header normalization.
    """
    
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

    def find_header_row(self, keywords: List[str], max_rows: int = 15, sheet_name: Optional[any] = 0) -> int:
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

        def mapper(col: str) -> str:
            if any(h.lower() in col.lower() for h in self.CHARGEABILITY_HEADERS):
                return "chargeability"
            return col.lower().replace(" ", "_")

        self.df.columns = [mapper(str(c)).strip() for c in self.df.columns]
        
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
                self.df[col] = self.df[col].apply(
                    lambda x: 1 if str(x).strip().upper() == 'D' else x
                )
                # Force numeric, turning other errors into NaN then 0
                self.df[col] = pd.to_numeric(self.df[col], errors='coerce').fillna(0).astype(int)

    def clean(self):
        """Main entry point for cleaning. To be overridden by subclasses."""
        self.normalize_headers()
