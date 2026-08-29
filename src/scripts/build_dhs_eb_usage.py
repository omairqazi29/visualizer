"""Regenerate the EB_TOTAL rows of `data/DHS_Yearbook/dhs_eb_category_usage.csv`.

`docs/POLICY_VERIFICATION.md` refers to "the extraction script" for this CSV;
this is it, for the total/aos/consular split.

Source: DHS Yearbook Tables 8-11 "New Arrivals / Adjustments of Status"
workbooks in `data/DHS_Yearbook/*tables8-11*.xlsx`, read via
`src.parsers.dhs_newadj_parser`. Table 10 of those files reports
employment-based preferences separately for new arrivals (consular) and
adjustments of status (AOS), which is the only published source for that split.

Scope and safety:

- Only `EB_TOTAL` rows are written. Per-category rows (EB1-EB5) come from
  Table 7 and are never touched by this script.
- Existing rows are preserved by default. When the workbook disagrees with a
  row already in the CSV, the difference is reported and the existing value is
  kept unless `--overwrite` is passed. This matters because DHS rounds FY2023+
  releases to the nearest 10, so a derived total (aos + consular) can differ by
  ~10 from a total published elsewhere in the Yearbook.

Usage:
    python3 -m src.scripts.build_dhs_eb_usage [--overwrite] [--dry-run]
"""

import argparse
import csv
import sys
from pathlib import Path

from ..parsers.dhs_newadj_parser import DHSNewAdjParser


CSV_PATH = Path("data/DHS_Yearbook/dhs_eb_category_usage.csv")
FIELDNAMES = ["fiscal_year", "category", "total", "aos", "consular"]

# EB_TOTAL sorts ahead of the per-category rows within a fiscal year, matching
# the existing file's convention.
_CATEGORY_ORDER = {"EB_TOTAL": 0, "EB1": 1, "EB2": 2, "EB3": 3, "EB4": 4, "EB5": 5}


def _sort_key(row: dict) -> tuple:
    return (
        int(row["fiscal_year"]),
        _CATEGORY_ORDER.get(row["category"], 99),
        row["category"],
    )


def _read_existing(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def build(csv_path: Path, data_dir: str, overwrite: bool, dry_run: bool) -> int:
    rows = _read_existing(csv_path)
    index = {(r["fiscal_year"], r["category"]): r for r in rows}

    parser = DHSNewAdjParser(data_dir)
    splits = parser.get_eb_splits()
    if not splits:
        print("No tables8-11 workbooks found; nothing to do.", file=sys.stderr)
        return 1

    added, updated, kept, skipped = [], [], [], []

    for split in splits:
        if split.aos is None or split.consular is None:
            skipped.append(split.fiscal_year)
            continue

        key = (str(split.fiscal_year), "EB_TOTAL")
        new_row = {
            "fiscal_year": str(split.fiscal_year),
            "category": "EB_TOTAL",
            "total": str(split.total),
            "aos": str(split.aos),
            "consular": str(split.consular),
        }

        existing = index.get(key)
        if existing is None:
            rows.append(new_row)
            index[key] = new_row
            added.append(split.fiscal_year)
            continue

        differs = any(existing.get(f) != new_row[f] for f in ("total", "aos", "consular"))
        if not differs:
            kept.append(split.fiscal_year)
        elif overwrite:
            existing.update(new_row)
            updated.append((split.fiscal_year, dict(existing), new_row))
        else:
            kept.append(split.fiscal_year)
            print(
                f"  FY{split.fiscal_year}: workbook says "
                f"total={new_row['total']} aos={new_row['aos']} consular={new_row['consular']}; "
                f"CSV has total={existing.get('total')} aos={existing.get('aos')} "
                f"consular={existing.get('consular')} (kept CSV; pass --overwrite to replace)"
            )

    rows.sort(key=_sort_key)

    print(f"\nadded EB_TOTAL rows for: {added or 'none'}")
    print(f"already consistent:      {kept or 'none'}")
    if updated:
        print(f"overwritten:             {[u[0] for u in updated]}")
    if skipped:
        print(f"no EB split available:   {skipped}")

    if dry_run:
        print("\n--dry-run: no file written")
        return 0

    with open(csv_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in FIELDNAMES})
    print(f"\nwrote {csv_path} ({len(rows)} rows)")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--csv", default=str(CSV_PATH), help="target CSV path")
    ap.add_argument("--data-dir", default="data/DHS_Yearbook", help="directory holding the workbooks")
    ap.add_argument("--overwrite", action="store_true", help="replace existing EB_TOTAL rows that disagree")
    ap.add_argument("--dry-run", action="store_true", help="report changes without writing")
    args = ap.parse_args()
    return build(Path(args.csv), args.data_dir, args.overwrite, args.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
