#!/usr/bin/env python3
"""
Data Update Utility for The Spillover Engine.

Fetches or prepares latest DOS IV issuance reports and USCIS EB Inventory / pipeline files.
Since official sites require manual download (no stable public API for Excel),
this script:
- Prints instructions with latest known URLs (research-verified)
- Validates any user-placed new files in data/DOS/ or data/ using auto-discovery
- Re-runs parsers on the discovered latest files for sanity

The engine (api + SupplyCalculator + parsers) now auto-discovers the newest matching
eb_inventory*.xlsx and *performance*.xlsx / eb_i140*.xlsx via filename date or mtime.
DOS loads *every* file in data/DOS/ whose name matches the month-year prefix (new bulletins
just work if naming convention followed).

Usage: python -m src.scripts.update_data

Research note (INA/news): Always cross-check travel.state.gov for newest monthly
"IV Issuances by FSC..." and uscis.gov for "Employment-Based Adjustment of Status Inventory".
Research baselines (e.g. DEFAULT_INDIA_EB1_SUPPLY) are from the 2026 snapshot; runtime
demand numbers always come from the latest discovered files in data/.
"""

import sys
from pathlib import Path

# Add project root
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.parsers.dos_parser import DOSParser
from src.parsers.inventory_parser import InventoryParser
from src.parsers.pipeline_parser import PipelineParser
from src.data_discovery import (
    get_latest_inventory_path,
    get_latest_pipeline_path,
    get_dos_dir,
)


def main():
    print("=" * 60)
    print("Spillover Engine - Data Refresh Helper")
    print("=" * 60)
    print()
    print("1. Download latest files manually:")
    print("   - DOS Monthly:")
    print(
        "     https://travel.state.gov/content/travel/en/legal/visa-law0/visa-statistics/immigrant-visa-statistics/monthly-immigrant-visa-issuances.html"
    )
    print(
        "     (New files named e.g. 'OCTOBER 2025 - ...xlsx' in data/DOS/ are auto-loaded)"
    )
    print("   - USCIS EB I-485 Inventory:")
    print(
        "     https://www.uscis.gov/tools/reports-and-studies/immigration-and-citizenship-data"
    )
    print(
        "     (Any eb_inventory_*.xlsx dropped in data/ becomes current via discovery)"
    )
    print(
        "   - I-140 Performance / Pipeline (eb_i140* or performance data): same USCIS page"
    )
    print(
        "   - Visa Bulletins and annual reports: travel.state.gov (research aids only)"
    )
    print()
    print(
        "2. Place new DOS xlsx into data/DOS/ (filename format: 'MONTH YYYY - ... .xlsx')"
    )
    print(
        "3. Add/replace eb_inventory_*.xlsx or pipeline *.xlsx in data/ (latest by name date wins)"
    )
    print()
    print(
        "The runtime uses auto-discovered latest files (see data_discovery.py). Researched constants are snapshot-based."
    )
    print(
        "Real policy: Presidential Proclamations restrict specific countries (India excluded) -> extra spillover via apply_real_restrictions flag."
    )
    print()
    print("Validating current (discovered) data files...")

    # DOS (directory load — already supported drop-in new bulletins)
    dos_dir = Path(get_dos_dir())
    if dos_dir.exists():
        dos_files = list(dos_dir.glob("*.xlsx"))
        print(f"  Found {len(dos_files)} DOS files (all loaded by DOSParser).")
        try:
            df = DOSParser.load_from_directory(str(dos_dir))
            print(f"  DOSParser combined rows: {len(df)}")
        except Exception as e:
            print(f"  DOS parse warning: {e}")

    # Inventory + pipeline now via discovery (new files "just work")
    inv_path = Path(get_latest_inventory_path())
    print(f"  Using inventory: {inv_path.name} (discovered or fallback)")
    if inv_path.exists():
        try:
            p = InventoryParser(str(inv_path))
            stats = p.get_india_eb1_queue()
            print(f"  Inventory India EB-1 total (2.2x): {stats['total']}")
        except Exception as e:
            print(f"  Inventory parse warning: {e}")
    else:
        print("  Warning: Inventory file missing.")

    pipe_path = Path(get_latest_pipeline_path())
    print(f"  Using pipeline: {pipe_path.name} (discovered or fallback)")
    if pipe_path.exists():
        try:
            pp = PipelineParser(str(pipe_path))
            pp.load_data()
            pback = pp.get_india_eb1_backlog()
            print(f"  Pipeline India EB-1 backlog (2.2x): {pback}")
        except Exception as e:
            print(f"  Pipeline parse warning: {e}")
    else:
        print("  Warning: Pipeline file missing.")

    print("\nData refresh complete. Re-run API tests or `docker-compose up --build`.")
    print(
        "For full revamp, consider adding a simple HTTP fetcher for known report pages + pandas read."
    )


if __name__ == "__main__":
    main()
