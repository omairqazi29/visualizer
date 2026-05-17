#!/usr/bin/env python3
"""
Data Update Utility for The Spillover Engine.

Fetches or prepares latest DOS IV issuance reports and USCIS EB Inventory files.
Since official sites require manual download (no stable public API for Excel),
this script:
- Prints instructions with latest known URLs (research-verified as of 2026)
- Validates any user-placed new files in data/DOS/ or data/
- Re-runs parsers on new files for sanity

Usage: python -m src.scripts.update_data

Research note (INA/news): Always cross-check travel.state.gov for newest monthly
"IV Issuances by FSC..." and uscis.gov for "Employment-Based Adjustment of Status Inventory".
Current as of mid-2026: DOS through Sep 2025 (FY2025, no FY2026 Excel published yet),
USCIS Jan 2026 inventory (latest). No INA 201/203 statutory changes. Real (non-hypo)
travel/visa restrictions via 2025-26 Proclamations on specific countries (India excluded)
provide additional spillover not in FY2025 DOS data; see ACTUAL_RESTRICTED_COUNTRIES.
"""

import os
import sys
from pathlib import Path

# Add project root
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.parsers.dos_parser import DOSParser
from src.parsers.inventory_parser import InventoryParser


def main():
    print("=" * 60)
    print("Spillover Engine - Data Refresh Helper")
    print("=" * 60)
    print()
    print("1. Download latest files manually:")
    print("   - DOS Monthly (FY2025 latest, no FY2026 Excel as of May 2026):")
    print("     https://travel.state.gov/content/travel/en/legal/visa-law0/visa-statistics/immigrant-visa-statistics/monthly-immigrant-visa-issuances.html")
    print("     Direct e.g. Sep 2025: https://travel.state.gov/content/dam/visas/Statistics/Immigrant-Statistics/MonthlyIVIssuances/Excel/FY2025/SEPTEMBER%202025%20-%20IV%20Issuances%20by%20FSC%20or%20Place%20of%20Birth%20and%20Visa%20Class.xlsx")
    print("   - USCIS EB I-485 Inventory (latest Jan 2026):")
    print("     https://www.uscis.gov/tools/reports-and-studies/immigration-and-citizenship-data")
    print("     Direct: https://www.uscis.gov/sites/default/files/document/data/eb_inventory_january_2026.xlsx")
    print("   - Visa Bulletins (India EB-1 FAD 01APR23 in May 2026): https://travel.state.gov/content/travel/en/legal/visa-law0/visa-bulletin/2026/visa-bulletin-for-may-2026.html")
    print("   - Report of the Visa Office 2024 (key: India EB-1 6952 visas issued): https://travel.state.gov/content/travel/en/legal/visa-law0/visa-statistics/annual-reports/report-of-the-visa-office-2024.html")
    print()
    print("2. Place new DOS xlsx into data/DOS/ (filename format: 'MONTH YYYY - ... .xlsx')")
    print("3. Replace or add eb_inventory_january_2026.xlsx (or newer) in data/")
    print()
    print("Key researched numbers (Jan 2026 inventory, 2.2x): India EB-1 I-485 pending total 48162 (primary ~27962); I-140 pipeline 45302 (primary ~20592).")
    print("Real policy: Presidential Proclamations 10949/10998 restrict specific countries (not 75, India excluded) -> extra real spillover modeled via apply_real_restrictions.")
    print()
    print("Validating current data files...")

    dos_dir = Path("data/DOS")
    if dos_dir.exists():
        dos_files = list(dos_dir.glob("*.xlsx"))
        print(f"  Found {len(dos_files)} DOS files.")
        try:
            df = DOSParser.load_from_directory(str(dos_dir))
            print(f"  DOSParser combined rows: {len(df)}")
        except Exception as e:
            print(f"  DOS parse warning: {e}")

    inv_path = Path("data/eb_inventory_january_2026.xlsx")
    if inv_path.exists():
        try:
            p = InventoryParser(str(inv_path))
            stats = p.get_india_eb1_queue()
            print(f"  Inventory India EB-1 total (2.2x): {stats['total']}")
        except Exception as e:
            print(f"  Inventory parse warning: {e}")
    else:
        print("  Warning: Inventory file missing.")

    print("\nData refresh complete. Re-run API tests or `docker-compose up --build`.")
    print("For full revamp, consider adding a simple HTTP fetcher for known report pages + pandas read.")


if __name__ == "__main__":
    main()