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
from dataclasses import asdict
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


def _capture() -> dict:
    """Run the current engine and return a reference snapshot dict."""
    from src.engine.supply import SupplyCalculator

    calc = SupplyCalculator()

    std = calc.get_supply_breakdown(apply_freeze=False, apply_real_restrictions=False)
    freeze = calc.get_supply_breakdown(apply_freeze=True, apply_real_restrictions=False)
    real = calc.get_supply_breakdown(apply_freeze=False, apply_real_restrictions=True)

    snapshot = {
        "captured_at": datetime.now().isoformat(),
        "engine_version": "pre-refactor",
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

    # Quick smoke check: known integers
    std_ref = reference.get("standard", {})
    for key, expected in KNOWN_INTEGERS.items():
        if key == "india_eb1_supply_std":
            actual = std_ref.get("india_eb1_supply")
        elif key == "eb_base_limit":
            actual = std_ref.get("eb_base_limit")
        elif key == "fb_statutory_limit":
            # Not stored directly; skip for now
            continue
        else:
            continue

        if actual is not None and actual != expected:
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
