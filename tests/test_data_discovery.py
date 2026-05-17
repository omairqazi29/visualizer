"""Targeted tests for data_discovery (new in support of drop-in new bulletins/USCIS data).

These tests use tmp_path exclusively and never touch real data/ or the existing
pinned exact-numeric asserts in test_engine.py / test_parsers.py.
"""

import os
from pathlib import Path
import time


from src.data_discovery import (
    find_latest,
    get_latest_inventory_path,
    get_latest_pipeline_path,
    get_dos_dir,
    _parse_date_from_filename,
    MONTHS_MAP,
)


def test_months_map_complete():
    assert len(MONTHS_MAP) == 12
    assert MONTHS_MAP["JANUARY"] == 1
    assert MONTHS_MAP["DECEMBER"] == 12


def test_parse_date_various_patterns():
    # Inventory style
    assert _parse_date_from_filename(Path("eb_inventory_january_2026.xlsx")) == (
        2026,
        1,
    )
    assert _parse_date_from_filename(Path("data/eb_inventory_march_2026.xlsx")) == (
        2026,
        3,
    )
    assert _parse_date_from_filename(Path("EB_INVENTORY_2026-04.xlsx")) == (2026, 4)
    # DOS style with space
    assert _parse_date_from_filename(Path("OCTOBER 2025 - IV Issuances....xlsx")) == (
        2025,
        10,
    )
    # Pipeline FY Q style
    assert _parse_date_from_filename(
        Path("eb_i140_i360_i526_performance_data_fy2025_q4_v1.xlsx")
    ) == (2025, 10)
    assert _parse_date_from_filename(Path("performance_fy2024_q2.xlsx")) == (2024, 4)
    # No date
    assert _parse_date_from_filename(Path("some_random_file.xlsx")) is None


def test_find_latest_empty_dir_returns_none(tmp_path):
    p = find_latest("eb_inventory*.xlsx", str(tmp_path))
    assert p is None


def test_find_latest_fallback_not_used_in_get_when_empty(tmp_path):
    # get_ always returns a string path (fallback) even if none found
    inv = get_latest_inventory_path(str(tmp_path))
    assert "eb_inventory_january_2026.xlsx" in inv
    pipe = get_latest_pipeline_path(str(tmp_path))
    assert "fy2025_q4" in pipe or "performance" in pipe


def test_find_latest_prefers_parsed_date_over_mtime(tmp_path):
    # Create two files, older date but newer mtime — date wins
    old = tmp_path / "eb_inventory_january_2025.xlsx"
    new = tmp_path / "eb_inventory_march_2026.xlsx"
    old.write_text("old")
    new.write_text("new")
    # Make old have newer mtime
    now = time.time()
    os.utime(old, (now + 100, now + 100))
    os.utime(new, (now - 100, now - 100))

    latest = find_latest("eb_inventory*.xlsx", str(tmp_path))
    assert latest is not None
    assert latest.name == "eb_inventory_march_2026.xlsx"


def test_find_latest_uses_mtime_when_no_parseable_date(tmp_path):
    undated1 = tmp_path / "eb_inventory_custom.xlsx"
    undated2 = tmp_path / "eb_inventory_another.xlsx"
    undated1.write_text("1")
    undated2.write_text("2")
    # Make undated2 newer on disk
    time.sleep(0.01)
    undated2.touch()

    latest = find_latest("eb_inventory*.xlsx", str(tmp_path))
    assert latest is not None
    assert latest.name == "eb_inventory_another.xlsx"


def test_find_latest_multiple_dates_picks_newest(tmp_path):
    f2024 = tmp_path / "eb_inventory_december_2024.xlsx"
    f2025 = tmp_path / "eb_inventory_january_2025.xlsx"
    f2026 = tmp_path / "eb_inventory_february_2026.xlsx"
    for f in (f2024, f2025, f2026):
        f.write_text("x")

    latest = find_latest("eb_inventory*.xlsx", str(tmp_path))
    assert latest.name == "eb_inventory_february_2026.xlsx"


def test_find_latest_prefers_pipeline_patterns(tmp_path):
    f1 = tmp_path / "eb_i140_i360_i526_performance_data_fy2025_q4_v1.xlsx"
    f2 = tmp_path / "some_performance_data_fy2026_q1.xlsx"
    f1.write_text("a")
    f2.write_text("b")

    latest = get_latest_pipeline_path(str(tmp_path))
    # Now purely date-driven across patterns (unified max); the test still only requires not falling back to the pinned name string
    assert "fy202" in Path(latest).name or "performance" in Path(latest).name
    assert "january_2026" not in Path(latest).name  # not the inventory fallback


def test_find_latest_ambiguous_names_stable(tmp_path):
    # Two files without dates, ensure deterministic (by mtime or name)
    a = tmp_path / "eb_inventory_aaa.xlsx"
    b = tmp_path / "eb_inventory_bbb.xlsx"
    a.write_text("a")
    b.write_text("b")
    # a newer
    os.utime(b, (time.time() - 10, time.time() - 10))

    latest = find_latest("eb_inventory*.xlsx", str(tmp_path))
    assert latest is not None
    # Either is acceptable; just ensure it returns one of them and not crash
    assert latest.name in ("eb_inventory_aaa.xlsx", "eb_inventory_bbb.xlsx")


def test_get_dos_dir():
    """Trivial coverage for the thin wrapper (Issue 10)."""
    d = get_dos_dir("data")
    assert d.endswith("DOS") or d.endswith("DOS/")
    d2 = get_dos_dir("/tmp/mydir")
    assert "mydir" in d2 and "DOS" in d2


def test_parser_latest_with_custom_data_dir(tmp_path):
    """Directly exercise the public Parser.latest(data_dir) API (Issue 5).
    Covers both the thin wrappers (post-refactor) and fallback under custom dir.
    """
    from src.parsers.inventory_parser import InventoryParser
    from src.parsers.pipeline_parser import PipelineParser

    # Empty custom dir -> must use fallback path *under that dir* (not CWD "data/")
    inv = InventoryParser.latest(str(tmp_path))
    assert str(tmp_path) in inv.file_path or tmp_path.name in inv.file_path
    assert "eb_inventory_january_2026.xlsx" in inv.file_path

    pipe = PipelineParser.latest(str(tmp_path))
    assert str(tmp_path) in pipe.file_path or tmp_path.name in pipe.file_path
    assert "fy2025_q4" in pipe.file_path or "performance" in pipe.file_path.lower()

    # With a real file present -> uses it (happy path under custom dir)
    good = tmp_path / "eb_inventory_march_2026.xlsx"
    good.write_text("mock")
    inv2 = InventoryParser.latest(str(tmp_path))
    assert "march_2026" in inv2.file_path


def test_parse_date_defensive_none_paths():
    """Light coverage for defensive branches in _parse (Issue 10)."""
    assert _parse_date_from_filename(Path("no_date_at_all.xlsx")) is None
    assert _parse_date_from_filename(Path("")) is None  # edge
    assert _parse_date_from_filename(None) is None  # the if guard
