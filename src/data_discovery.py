"""Data file auto-discovery for drop-in new bulletins, USCIS EB inventory, and pipeline data.

Enables "just drop the new file" workflow:
- New DOS monthly bulletins in data/DOS/ (already worked via load_from_directory + name regex).
- Newer eb_inventory_*.xlsx (e.g. eb_inventory_march_2026.xlsx) in data/.
- Newer eb_i140* or *performance*.xlsx pipeline files in data/.

The latest is selected by:
1. Parsed date from filename (preferred for human-named releases).
2. File mtime as tie-breaker / fallback for undated names.
3. Lexical name for final determinism.

This module is pure (no side effects, no pandas), safe (only reads trusted data/ dir).

Used by:
- InventoryParser.latest() / PipelineParser.latest()
- api/main.py endpoints
- src/scripts/update_data.py validation

Fallbacks always return the original pinned filenames so existing behavior and tests are unchanged unless a newer file is present.
"""

from pathlib import Path
from typing import Optional, Tuple
import fnmatch
import re

MONTHS_MAP = {
    "JANUARY": 1,
    "FEBRUARY": 2,
    "MARCH": 3,
    "APRIL": 4,
    "MAY": 5,
    "JUNE": 6,
    "JULY": 7,
    "AUGUST": 8,
    "SEPTEMBER": 9,
    "OCTOBER": 10,
    "NOVEMBER": 11,
    "DECEMBER": 12,
}


def parse_date_from_filename(path: Path | None) -> Optional[Tuple[int, int]]:
    """Return (year, month) tuple parsed from common government filename patterns.

    Supported patterns (case-insensitive):
    - Month names: eb_inventory_january_2026.xlsx, "JANUARY 2026 - ...xlsx", _FEBRUARY_2026
    - ISO-ish: eb_inventory_2026-03.xlsx, 2026_03
    - Fiscal: eb_i140_..._fy2025_q4_v1.xlsx or performance_fy2025_q4 -> treats Q4 as month 10 (Oct)
      Q1->1, Q2->4, Q3->7, Q4->10 for monotonic "newer" ordering within year.
    - Also plain 2025q4 etc.

    Returns None if no recognizable date (caller falls back to mtime).
    """
    if path is None:
        return None
    name = path.name.upper()

    # 1. Month name + year (handles DOS style and inventory style with spaces/underscores)
    for mname, mnum in MONTHS_MAP.items():
        # _JANUARY_2026 , JANUARY_2026 , JANUARY 2026 , JANUARY2026 , etc.
        patterns = [
            rf"_{re.escape(mname)}_(\d{{4}})",
            rf"_{re.escape(mname)}(\d{{4}})",
            rf"\b{re.escape(mname)}\s+(\d{{4}})\b",
            rf"\b{re.escape(mname)}(\d{{4}})\b",
            rf"{re.escape(mname)}_(\d{{4}})",
        ]
        for pat in patterns:
            m = re.search(pat, name)
            if m:
                try:
                    year = int(m.group(1))
                    return (year, mnum)
                except (IndexError, ValueError):
                    continue

    # 2. Year-month numeric: 2026-03, 2026_03, _2026-03- etc (take first two groups)
    m = re.search(r"(\d{4})[-_](\d{1,2})", name)
    if m:
        try:
            year = int(m.group(1))
            mon = int(m.group(2))
            if 1 <= mon <= 12:
                return (year, mon)
        except ValueError:
            pass

    # 3. FY + quarter (common for pipeline/ performance reports)
    # fy2025_q4 , _FY2025-Q4 , 2025q4 etc. Map Q to representative month.
    m = re.search(r"(?:FY|Q)?(\d{4})[_-]?Q([1-4])", name)
    if m:
        try:
            year = int(m.group(1))
            q = int(m.group(2))
            # Representative month for quarter end-ish (Q4 latest in FY)
            qmonth = {1: 1, 2: 4, 3: 7, 4: 10}[q]
            return (year, qmonth)
        except (IndexError, ValueError, KeyError):
            pass

    return None


def _file_sort_key(p: Path) -> tuple[int, int, float, str]:
    """Stable sort key for 'latest' selection (used by find_latest and cross-pattern getters).

    Primary: (year, month) from filename parse (or 0,0 for undated).
    Secondary: mtime (newer wins).
    Tertiary: name for determinism.
    """
    date = parse_date_from_filename(p)
    try:
        mtime = p.stat().st_mtime
    except (OSError, FileNotFoundError):
        mtime = 0.0
    if date is not None:
        return (date[0], date[1], mtime, p.name)
    else:
        return (0, 0, mtime, p.name)


def find_latest(pattern: str, data_dir: str = "data") -> Optional[Path]:
    """Return the Path to the newest file matching the glob pattern under data_dir.

    Selection order (descending):
    - Parsed (year, month) from filename (newer dates win)
    - If no parseable date: file mtime (newer files win)
    - Final tie-break: filename lexical (for determinism)

    pattern examples:
        "eb_inventory*.xlsx"
        "*performance*.xlsx"
        "eb_i140*.xlsx"

    The glob is performed as data_dir / pattern (flat only; pattern normalized to basename, no recursive ** support).
    Returns None if no matches or dir missing.
    """
    dir_path = Path(data_dir)
    if not dir_path.is_dir():
        return None

    # Support caller passing "eb_*.xlsx" or already "data/..." but normalize to relative pattern
    if pattern.startswith(str(dir_path)) or pattern.startswith(data_dir):
        # strip leading dir if user passed full
        pattern = Path(pattern).name  # keep simple, assume flat data/

    candidates = list(dir_path.glob(pattern))
    if not candidates:
        # Fallback using case-folded fnmatch to provide case-insensitive recovery on
        # case-sensitive filesystems (e.g. Linux) when primary glob() misses due to case.
        # (Primary glob() path + project filenames use matching case.)
        candidates = [
            p
            for p in dir_path.iterdir()
            if p.is_file()
            and p.suffix.lower() == ".xlsx"
            and fnmatch.fnmatch(p.name.lower(), pattern.lower())
        ]
        if not candidates:
            return None

    candidates = sorted(candidates, key=_file_sort_key, reverse=True)
    return candidates[0] if candidates else None


def get_latest_inventory_path(data_dir: str = "data") -> str:
    """Convenience: latest eb_inventory*.xlsx or the well-known fallback name."""
    p = find_latest("eb_inventory*.xlsx", data_dir)
    if p is not None:
        return str(p)
    # Preserve original default so nothing breaks when no newer file present
    return str(Path(data_dir) / "eb_inventory_january_2026.xlsx")


def get_latest_pipeline_path(data_dir: str = "data") -> str:
    """Convenience: the single overall newest pipeline file (by parsed date/mtime) across
    common naming patterns (eb_i140*.xlsx or *performance*.xlsx), or the well-known fallback.

    This is purely date-driven (no naming-group bias): a newer-dated file under either
    pattern wins. Callers (including PipelineParser.latest) get the true latest release.
    """
    p1 = find_latest("eb_i140*.xlsx", data_dir)
    p2 = find_latest("*performance*.xlsx", data_dir)
    cands = [p for p in (p1, p2) if p is not None]
    if cands:
        # Pick overall winner using the shared date/mtime/name key (cross-pattern correct)
        best = max(cands, key=_file_sort_key)
        return str(best)
    return str(Path(data_dir) / "eb_i140_i360_i526_performance_data_fy2025_q4_v1.xlsx")


def get_dos_dir(data_dir: str = "data") -> str:
    """Thin wrapper for consistency with inventory/pipeline getters (DOS already directory-based)."""
    return str(Path(data_dir) / "DOS")


__all__ = [
    "MONTHS_MAP",
    "parse_date_from_filename",
    "find_latest",
    "get_latest_inventory_path",
    "get_latest_pipeline_path",
    "get_dos_dir",
]
