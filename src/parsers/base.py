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

    def load_data(self, **kwargs) -> pd.DataFrame:
        """Loads the data based on file extension."""
        if self.file_path.endswith('.csv'):
            self.df = pd.read_csv(self.file_path, **kwargs)
        elif self.file_path.endswith(('.xlsx', '.xls')):
            self.df = pd.read_excel(self.file_path, **kwargs)
        else:
            raise ValueError(f"Unsupported file format: {self.file_path}")
        return self.df

    def normalize_headers(self):
        """Standardizes common headers to a single canonical name."""
        if self.df is None:
            return

        def mapper(col: str) -> str:
            if any(h.lower() in col.lower() for h in self.CHARGEABILITY_HEADERS):
                return "chargeability"
            return col.lower().replace(" ", "_")

        self.df.columns = [mapper(str(c)) for c in self.df.columns]

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
