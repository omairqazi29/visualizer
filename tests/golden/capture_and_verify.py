"""Golden reference capture and verification utility.

Usage:
    python -m tests.golden.capture_and_verify --capture      # write reference JSON
    python -m tests.golden.capture_and_verify --verify       # compare against references
    python -m tests.golden.capture_and_verify --regenerate   # dev-only: intentional update

Capture mode runs the current engine on live data and writes reference JSON
files to tests/golden/references/.  Verify mode loads references, runs the
current implementation, and asserts exact match on integers and float
tolerance 1e-9.

The ``--regenerate`` flag is an alias for ``--capture`` intended for use
after *intentional* model changes (new INA math, updated constants, etc.).
It is never invoked by CI.
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# Add project root to path for direct invocation
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

REFERENCES_DIR = Path(__file__).resolve().parent / "references"

# Float tolerance for verify mode
_FLOAT_TOL = 1e-9

# Key integers that must be exact-matched in verify mode
KNOWN_INTEGERS = {
    "india_eb1_supply_std": 6952,
    "india_eb1_supply_freeze": 78837,
    "india_eb1_supply_real": 31053,
    "fb_statutory_limit": 226000,
    "eb_base_limit": 140000,
}

# Maps KNOWN_INTEGERS keys to their location in the captured snapshot
_KNOWN_INT_PATHS = {
    "india_eb1_supply_std": ("standard", "india_eb1_supply"),
    "india_eb1_supply_freeze": ("freeze", "india_eb1_supply"),
    "india_eb1_supply_real": ("real_restrictions", "india_eb1_supply"),
    "fb_statutory_limit": ("constants", "fb_statutory_limit"),
    "eb_base_limit": ("standard", "eb_base_limit"),
}

# Scenario names and their config for capture
_SCENARIOS = {
    "standard": {"apply_freeze": False, "apply_real_restrictions": False},
    "freeze": {"apply_freeze": True, "apply_real_restrictions": False},
    "real_restrictions": {"apply_freeze": False, "apply_real_restrictions": True},
}

# Fields in each scenario breakdown — derived from the dataclass definition
# to stay in sync automatically if SupplyBreakdown changes.
def _get_breakdown_fields() -> list[str]:
    from dataclasses import fields as dc_fields
    from src.engine.supply import SupplyBreakdown
    return [f.name for f in dc_fields(SupplyBreakdown)]


_BREAKDOWN_FIELDS = _get_breakdown_fields()


def _capture_parser_metadata() -> dict:
    """Capture parser-specific metadata (column names, row counts)."""
    parser_meta: dict = {}

    try:
        from src.parsers.dos_parser import DOSParser
        from src.data_discovery import get_dos_dir
        dos_dir = get_dos_dir()
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


def _to_native(val):
    """Convert numpy/pandas numeric types to native Python for JSON."""
    if hasattr(val, 'item'):
        return val.item()
    return val


def _breakdown_to_dict(bd) -> dict:
    """Convert a SupplyBreakdown dataclass to a serialisable dict."""
    return {field: _to_native(getattr(bd, field)) for field in _BREAKDOWN_FIELDS}


def _capture() -> dict:
    """Run the current engine and return a reference snapshot dict."""
    from src.engine.supply import SupplyCalculator
    from src.constants import FB_STATUTORY_LIMIT

    calc = SupplyCalculator()

    results = {}
    for name, kwargs in _SCENARIOS.items():
        bd = calc.get_supply_breakdown(**kwargs)
        results[name] = _breakdown_to_dict(bd)

    snapshot = {
        "captured_at": datetime.now(tz=timezone.utc).isoformat(),
        "engine_version": "pr7-goldens",
        "constants": {
            "fb_statutory_limit": FB_STATUTORY_LIMIT,
        },
        **results,
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

    # Also write per-scenario files for clarity
    for scenario in _SCENARIOS:
        scenario_path = REFERENCES_DIR / f"waterfall_{scenario}.json"
        with open(scenario_path, "w") as f:
            json.dump(snapshot[scenario], f, indent=2)
        print(f"[golden] Wrote {scenario_path}")

    return out_path


def _values_equal(expected, actual, path: str = "") -> list[str]:
    """Recursively compare expected vs actual, returning list of mismatches.

    Integers: exact match.
    Floats: tolerance 1e-9.
    Strings/None: skipped (metadata like captured_at).
    Dicts: recurse.
    """
    errors: list[str] = []

    _SKIP_KEYS = ("captured_at", "engine_version", "parsers")

    if isinstance(expected, dict) and isinstance(actual, dict):
        for key in expected:
            if key in _SKIP_KEYS:
                continue  # metadata — skip
            child_path = f"{path}.{key}" if path else key
            if key not in actual:
                errors.append(f"MISSING: {child_path}")
                continue
            errors.extend(_values_equal(expected[key], actual[key], child_path))
        # Detect extra keys in actual that aren't in expected (shape change)
        for key in actual:
            if key in _SKIP_KEYS:
                continue
            child_path = f"{path}.{key}" if path else key
            if key not in expected:
                errors.append(f"EXTRA KEY: {child_path}")
    elif isinstance(expected, float) and isinstance(actual, (int, float)):
        if abs(expected - actual) > _FLOAT_TOL:
            errors.append(f"FLOAT MISMATCH: {path} expected={expected} actual={actual}")
    elif isinstance(expected, int) and isinstance(actual, int):
        if expected != actual:
            errors.append(f"INT MISMATCH: {path} expected={expected} actual={actual}")
    elif isinstance(expected, (str, type(None))):
        pass  # metadata — skip
    elif isinstance(expected, list) and isinstance(actual, list):
        if len(expected) != len(actual):
            errors.append(f"LEN MISMATCH: {path} expected={len(expected)} actual={len(actual)}")
        else:
            for i, (e, a) in enumerate(zip(expected, actual)):
                errors.extend(_values_equal(e, a, f"{path}[{i}]"))
    else:
        if expected != actual:
            errors.append(f"MISMATCH: {path} expected={expected} actual={actual}")

    return errors


def verify_against_reference() -> bool:
    """Load reference and verify current engine matches.

    Compares the full response shape (all scenario fields) plus exact-match
    on known critical integers (india_eb1_supply per scenario).
    """
    ref_path = REFERENCES_DIR / "supply_breakdown.json"
    if not ref_path.exists():
        print(f"[golden] No reference found at {ref_path}. Run --capture first.")
        return False

    with open(ref_path) as f:
        reference = json.load(f)

    # Step 1: Verify known critical integers from reference file
    for key, expected in KNOWN_INTEGERS.items():
        section, field = _KNOWN_INT_PATHS[key]
        actual = reference.get(section, {}).get(field)

        if actual is None:
            print(f"[golden] MISSING: {key} (section={section}, field={field})")
            return False
        if actual != expected:
            print(f"[golden] MISMATCH: {key} expected={expected} actual={actual}")
            return False

    # Step 2: Re-run current engine and compare full shapes
    try:
        current = _capture()
    except Exception as e:
        print(f"[golden] Engine run failed: {e}")
        return False

    errors = _values_equal(reference, current)
    if errors:
        for err in errors:
            print(f"[golden] {err}")
        return False

    print("[golden] Verify passed — all scenarios match reference.")
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description="Golden reference capture/verify")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--capture", action="store_true", help="Capture reference JSON")
    group.add_argument("--verify", action="store_true", help="Verify against reference")
    group.add_argument(
        "--regenerate", action="store_true",
        help="Dev-only: regenerate references after intentional model changes",
    )
    args = parser.parse_args()

    if args.capture or args.regenerate:
        if args.regenerate:
            print("[golden] REGENERATING references (intentional model update)")
        capture_to_file()
    elif args.verify:
        ok = verify_against_reference()
        sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
