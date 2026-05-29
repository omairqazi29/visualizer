"""Golden reference capture and verification utility.

Usage:
    python -m tests.golden.capture_and_verify --capture   # write reference JSON
    python -m tests.golden.capture_and_verify --verify    # compare against references

Capture mode runs the current engine on live data and writes reference JSON
files to tests/golden/references/.  Verify mode (PR7) loads references and
asserts exact match on key integers and float tolerance 1e-9.

This is a SKELETON in PR1 — capture works, full verify logic comes in PR7.
"""

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

# Add project root to path for direct invocation
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

REFERENCES_DIR = Path(__file__).resolve().parent / "references"

# Key integers that must be exact-matched in verify mode
KNOWN_INTEGERS = {
    "india_eb1_supply_std": 6952,
    "fb_statutory_limit": 226000,
    "eb_base_limit": 140000,
}

# Maps KNOWN_INTEGERS keys to their location in the captured snapshot
_KNOWN_INT_PATHS = {
    "india_eb1_supply_std": ("standard", "india_eb1_supply"),
    "fb_statutory_limit": ("constants", "fb_statutory_limit"),
    "eb_base_limit": ("standard", "eb_base_limit"),
}


def _capture_parser_metadata() -> dict:
    """Capture parser-specific metadata (column names, row counts)."""
    parser_meta = {}

    try:
        from src.parsers.dos_parser import DOSParser
        dos_dir = "data/dos_iv_data"
        if os.path.isdir(dos_dir):
            dos_df = DOSParser.load_from_directory(dos_dir)
            parser_meta["dos"] = {
                "columns": sorted(dos_df.columns.tolist()),
                "row_count": len(dos_df),
            }
    except Exception as e:
        parser_meta["dos"] = {"error": str(e)}

    try:
        from src.parsers.inventory_parser import InventoryParser
        inv = InventoryParser.latest()
        stats = inv.get_india_eb1_queue()
        parser_meta["inventory"] = {
            "queue": stats,
        }
    except Exception as e:
        parser_meta["inventory"] = {"error": str(e)}

    try:
        from src.parsers.pipeline_parser import PipelineParser
        pip = PipelineParser.latest()
        pip.load_data()
        if pip.df is not None:
            parser_meta["pipeline"] = {
                "columns": sorted(pip.df.columns.tolist()),
                "row_count": len(pip.df),
            }
    except Exception as e:
        parser_meta["pipeline"] = {"error": str(e)}

    return parser_meta


def _capture() -> dict:
    """Run the current engine and return a reference snapshot dict."""
    from src.engine.supply import SupplyCalculator

    calc = SupplyCalculator()

    std = calc.get_supply_breakdown(apply_freeze=False, apply_real_restrictions=False)
    freeze = calc.get_supply_breakdown(apply_freeze=True, apply_real_restrictions=False)
    real = calc.get_supply_breakdown(apply_freeze=False, apply_real_restrictions=True)

    from src.constants import FB_STATUTORY_LIMIT

    snapshot = {
        "captured_at": datetime.now().isoformat(),
        "engine_version": "pre-refactor",
        "constants": {
            "fb_statutory_limit": FB_STATUTORY_LIMIT,
        },
        "standard": {
            "eb_base_limit": std.eb_base_limit,
            "fb_spillover_std": std.fb_spillover_std,
            "fb_savings_freeze": std.fb_savings_freeze,
            "eb45_spillover_std": std.eb45_spillover_std,
            "eb45_savings_freeze": std.eb45_savings_freeze,
            "total_eb_supply": std.total_eb_supply,
            "eb1_supply": std.eb1_supply,
            "india_eb1_supply": std.india_eb1_supply,
        },
        "freeze": {
            "eb_base_limit": freeze.eb_base_limit,
            "fb_spillover_std": freeze.fb_spillover_std,
            "fb_savings_freeze": freeze.fb_savings_freeze,
            "eb45_spillover_std": freeze.eb45_spillover_std,
            "eb45_savings_freeze": freeze.eb45_savings_freeze,
            "total_eb_supply": freeze.total_eb_supply,
            "eb1_supply": freeze.eb1_supply,
            "india_eb1_supply": freeze.india_eb1_supply,
        },
        "real_restrictions": {
            "eb_base_limit": real.eb_base_limit,
            "fb_spillover_std": real.fb_spillover_std,
            "fb_savings_freeze": real.fb_savings_freeze,
            "eb45_spillover_std": real.eb45_spillover_std,
            "eb45_savings_freeze": real.eb45_savings_freeze,
            "total_eb_supply": real.total_eb_supply,
            "eb1_supply": real.eb1_supply,
            "india_eb1_supply": real.india_eb1_supply,
        },
        "parsers": _capture_parser_metadata(),
    }
    return snapshot


def capture_to_file() -> Path:
    """Capture current engine output and write to references directory."""
    REFERENCES_DIR.mkdir(parents=True, exist_ok=True)
    snapshot = _capture()
    out_path = REFERENCES_DIR / "supply_breakdown.json"
    with open(out_path, "w") as f:
        json.dump(snapshot, f, indent=2)
    print(f"[golden] Captured reference -> {out_path}")
    return out_path


def verify_against_reference() -> bool:
    """Load reference and verify current engine matches.

    Skeleton — full implementation in PR7.
    """
    ref_path = REFERENCES_DIR / "supply_breakdown.json"
    if not ref_path.exists():
        print(f"[golden] No reference found at {ref_path}. Run --capture first.")
        return False

    with open(ref_path) as f:
        reference = json.load(f)

    # Quick smoke check: known integers via path mapping
    for key, expected in KNOWN_INTEGERS.items():
        section, field = _KNOWN_INT_PATHS[key]
        actual = reference.get(section, {}).get(field)

        if actual is None:
            print(f"[golden] MISSING: {key} (section={section}, field={field})")
            return False
        if actual != expected:
            print(f"[golden] MISMATCH: {key} expected={expected} actual={actual}")
            return False

    print("[golden] Verify skeleton passed (full verify in PR7).")
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description="Golden reference capture/verify")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--capture", action="store_true", help="Capture reference JSON")
    group.add_argument("--verify", action="store_true", help="Verify against reference")
    args = parser.parse_args()

    if args.capture:
        capture_to_file()
    elif args.verify:
        ok = verify_against_reference()
        sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
