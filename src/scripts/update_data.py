#!/usr/bin/env python3
"""
Data Update Utility for The Spillover Engine.

Supports both the **automated** ingestion pipeline and the original **manual**
validation workflow.

## Automated flow (preferred)

Scan public DOS / USCIS pages, download new Excel files into `data/`, validate
with parsers, and optionally open a GitHub PR:

    python -m src.scripts.scan_and_pr --scan --dry-run
    python -m src.scripts.scan_and_pr --scan --fetch --validate --source dos_iv
    python -m src.scripts.scan_and_pr --scan --fetch --validate --pr --source all

GitHub Actions runs the same entrypoint on a schedule (see
`.github/workflows/data-scan.yml` and `data-scan-visa-bulletin.yml`).

Source registry: `src/ingestion/registry.py`
Scanner / fetcher / PR helper: `src/ingestion/`

## Manual flow (this module default)

Prints research-verified URLs, then validates currently discovered files in
`data/DOS/`, `data/eb_inventory_*.xlsx`, and pipeline xlsx via auto-discovery.

Usage:
    python -m src.scripts.update_data              # validate current data
    python -m src.scripts.update_data --scan       # delegate to scan_and_pr --scan
    python -m src.scripts.update_data --help-auto  # print automation help

Research note (INA/news): Always cross-check travel.state.gov for newest monthly
"IV Issuances by FSC..." and uscis.gov for "Employment-Based Adjustment of Status Inventory".
Research baselines (e.g. DEFAULT_INDIA_EB1_SUPPLY) are from the 2026 snapshot; runtime
demand numbers always come from the latest discovered files in data/.
"""

from __future__ import annotations

import argparse
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


def print_automation_help() -> None:
    print(
        """
Automated data ingestion
========================

CLI:
  python -m src.scripts.scan_and_pr --list-sources
  python -m src.scripts.scan_and_pr --scan --dry-run
  python -m src.scripts.scan_and_pr --scan --fetch --validate --source dos_iv
  python -m src.scripts.scan_and_pr --scan --fetch --validate --pr --source uscis

Source groups: all | dos_iv | visa_bulletin | uscis | uscis_inventory |
               uscis_i485_perf | uscis_i140 | dhs | dol | supply

GitHub Actions:
  .github/workflows/data-scan.yml            — scheduled + workflow_dispatch
  .github/workflows/data-scan-visa-bulletin.yml — faster VB cadence

After data merges, update the changelog in docs/POLICY_VERIFICATION.md if
supply/demand inputs changed. Visa Bulletin still needs CSV history rows in
data/visa_bulletin/ when a new bulletin posts (scanner records bulletin URLs).
""".strip()
    )


def validate_current_data() -> None:
    print("=" * 60)
    print("Spillover Engine - Data Refresh Helper")
    print("=" * 60)
    print()
    print("Automated scan/fetch/PR is available via:")
    print("  python -m src.scripts.scan_and_pr --scan --dry-run")
    print("  python -m src.scripts.update_data --help-auto")
    print()
    print("1. Download latest files (manual fallback):")
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
        "For scheduled ingestion, see .github/workflows/data-scan.yml "
        "or run: python -m src.scripts.scan_and_pr --scan --fetch --validate"
    )


def main(argv: list | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Spillover Engine data refresh helper (manual validate + automation pointer)"
    )
    parser.add_argument(
        "--scan",
        action="store_true",
        help="Delegate to scan_and_pr --scan (pass through extra args after --)",
    )
    parser.add_argument(
        "--help-auto",
        action="store_true",
        help="Print automated ingestion help and exit",
    )
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Only validate current data (default behavior)",
    )
    args, rest = parser.parse_known_args(argv)

    if args.help_auto:
        print_automation_help()
        return 0

    if args.scan:
        from src.scripts.scan_and_pr import main as scan_main

        # Forward remaining args; ensure --scan is set
        fwd = ["--scan"] + rest
        return scan_main(fwd)

    validate_current_data()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
