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
Current as of plan: DOS through Sep 2025, USCIS Jan 2026 inventory. FY2026 files will extend projections.
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
    print("   - DOS Monthly: https://travel.state.gov/content/travel/en/legal/visa-law0/visa-bulletin.html")
    print("     (Look for 'Immigrant Visa Issuances by ...' Excel links, FY2026 months)")
    print("   - USCIS Inventory: https://www.uscis.gov/green-card/green-card-processes-and-procedures/visa-availability-priority-dates (or search 'EB I-485 Inventory')")
    print()
    print("2. Place new DOS xlsx into data/DOS/ (filename format: 'MONTH YYYY - ... .xlsx')")
    print("3. Replace or add eb_inventory_january_2026.xlsx (or newer) in data/")
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