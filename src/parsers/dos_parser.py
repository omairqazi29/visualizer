from .base import BaseParser
import pandas as pd
import os

from ..data_discovery import MONTHS_MAP


class DOSParser(BaseParser):
    """
    Parser for DOS Monthly Issuance data.
    Calculates FB usage to determine potential spillover to EB categories.
    """

    FB_CATEGORIES = ["F1", "F2A", "F2B", "F3", "F4", "FX"]

    def load_data(
        self,
        prevent_recursion: bool = False,
        month: int = None,
        year: int = None,
        **kwargs
    ) -> pd.DataFrame:
        """Overridden to find header automatically for DOS format and inject date."""
        if not prevent_recursion:
            # Actual DOS files use 'Issuances' as the count column and
            # 'Foreign State of Chargeability' (or subset) for country
            self.find_header_row(["Foreign State", "Visa Class", "Issuances"])
        else:
            super().load_data(**kwargs)

        if self.df is not None and month is not None:
            self.df["report_month"] = month
            self.df["report_year"] = year

        return self.df

    @classmethod
    def load_from_directory(cls, dir_path: str) -> pd.DataFrame:
        """Loads all Excel files in a directory and concatenates them."""
        import re

        all_dfs = []
        # Shared MONTHS_MAP from data_discovery to avoid duplication (supports new bulletin filenames)
        months_map = MONTHS_MAP

        for file in os.listdir(dir_path):
            if file.endswith(".xlsx"):
                # Extract Month and Year from filename
                match = re.match(r"^([A-Z]+)\s+(\d{4})", file.upper())
                month_num = None
                year_num = None
                if match:
                    month_str = match.group(1)
                    month_num = months_map.get(month_str)
                    year_num = int(match.group(2))

                parser = cls(os.path.join(dir_path, file))
                parser.load_data(month=month_num, year=year_num)
                parser.clean()
                if parser.df is not None:
                    all_dfs.append(parser.df)

        if not all_dfs:
            return pd.DataFrame()

        combined_df = pd.concat(all_dfs, ignore_index=True)
        return combined_df

    def get_monthly_distribution(
        self, country: str = None, categories: list = None
    ) -> dict:
        """Calculates the historical distribution of issuances by month."""
        if (
            self.df is None
            or "count" not in self.df.columns
            or "report_month" not in self.df.columns
        ):
            # Fallback to even distribution if no data
            return {m: 1 / 12 for m in range(1, 13)}

        df = self.df.copy()
        if country and "chargeability" in df.columns:
            df = df[df["chargeability"].str.contains(country, case=False, na=False)]
        if categories and "visa_category" in df.columns:
            df = df[df["visa_category"].isin(categories)]

        monthly_totals = df.groupby("report_month")["count"].sum()
        total_issuances = monthly_totals.sum()

        if total_issuances == 0:
            return {m: 1 / 12 for m in range(1, 13)}

        dist = (monthly_totals / total_issuances).to_dict()
        # Fill missing months with 0
        return {m: dist.get(m, 0) for m in range(1, 13)}

    def clean(self):
        """Clean and normalize DOS specific data."""
        super().clean()

        # DOS files often have 'visa_class' or 'class_of_admission'
        def category_mapper(col: str) -> str:
            lower_col = col.lower()
            if any(
                h in lower_col for h in ["class", "category", "symbol", "admission"]
            ):
                return "visa_category"
            return col

        self.df.columns = [category_mapper(c) for c in self.df.columns]

        # Normalize the count column
        count_cols = [
            c
            for c in self.df.columns
            if "count" in c or "number" in c or "issuances" in c or "total" in c
        ]
        if count_cols:
            self.normalize_disclosure_values(count_cols)
            # Rename primary count col to 'count'
            self.df.rename(columns={count_cols[0]: "count"}, inplace=True)

    def get_total_fb_usage(self) -> int:
        """Returns the total issuances for FB categories."""
        if self.df is None or "visa_category" not in self.df.columns:
            return 0

        fb_df = self.df[self.df["visa_category"].isin(self.FB_CATEGORIES)]
        return fb_df["count"].sum()

    def get_fb_spillover(self, statutory_limit: int = 226000) -> int:
        """
        INA 201(c) spillover logic:
        Visas not used in FB (up to the 226k floor) spill over to EB.
        """
        usage = self.get_total_fb_usage()
        return max(0, statutory_limit - usage)

    def parse(self) -> pd.DataFrame:
        """Parse DOS data: load, clean, and return the DataFrame.

        Satisfies the Parser protocol from src.domain.protocols.

        NOTE: report_month / report_year columns are NOT injected here.
        Date metadata is only available when loading via load_from_directory(),
        which extracts month/year from filenames. get_monthly_distribution()
        falls back to even 1/12 distribution when date columns are absent.
        """
        self.load_data()
        self.clean()
        return self.df
