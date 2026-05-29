"""Pandas-based DOS data loader implementing DOSDataLoader protocol.

Wraps existing DOSParser.load_from_directory to satisfy the DOSDataLoader
protocol contract, enabling dependency injection into SupplyCalculator.
"""

import pandas as pd

from ..parsers.dos_parser import DOSParser


class PandasDOSLoader:
    """Implements DOSDataLoader protocol. Wraps existing DOSParser.load_from_directory."""

    def __init__(self, dos_dir: str = "data/DOS"):
        self._dos_dir = dos_dir

    def load_all_issuances(self) -> pd.DataFrame:
        """Load and return all DOS issuance records as a single DataFrame."""
        return DOSParser.load_from_directory(self._dos_dir)
