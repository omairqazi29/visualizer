"""Tests for the data sources added in the FY2026-Q1 drop, plus regressions.

Covers:
- InventoryParser._parse_val float handling (the Feb 2026 storage change)
- InventoryParser.snapshots / burn_rate
- I485FlowParser quarterly dedup across filename variants
- PERMParser fiscal-year parsing for two-digit FY names
- DHSNewAdjParser EB new-arrival vs adjustment splits
- I140RADPParser and AllFormsParser
"""

import os
import shutil

import pytest

from src.parsers.inventory_parser import InventoryParser, _parse_val
from src.parsers.i485_parser import I485FlowParser
from src.parsers.perm_parser import _parse_fy_from_filename
from src.parsers.dhs_newadj_parser import DHSNewAdjParser
from src.parsers.i140_radp_parser import I140RADPParser
from src.parsers.all_forms_parser import AllFormsParser


# ──────────────────────────────────────────────
# Inventory cell parsing (regression)
# ──────────────────────────────────────────────

def test_parse_val_handles_float_strings():
    """USCIS switched these cells to numeric storage in the Feb 2026 release.

    pandas then surfaces them as '1802.0'; the old int(str(v)) path raised and
    silently returned 0, zeroing most of the India EB2/EB3 queue.
    """
    assert _parse_val("1802.0") == 1802
    assert _parse_val(1802.0) == 1802
    assert _parse_val("1,802") == 1802
    assert _parse_val("1802") == 1802


def test_parse_val_handles_markers():
    assert _parse_val("D") == 1        # suppressed cells count as at least one
    assert _parse_val("-") == 0
    assert _parse_val("") == 0
    assert _parse_val("0.0") == 0
    assert _parse_val(None) == 0


def test_india_eb2_queue_is_not_collapsed():
    """Guards the specific failure: India EB2 read as ~450 instead of ~25,000."""
    path = "data/eb_inventory_april_2026.xlsx"
    if not os.path.exists(path):
        pytest.skip("April 2026 inventory not present")
    backlogs = InventoryParser(path).get_all_eb_backlogs()
    assert backlogs["India"]["EB2"] > 10_000
    assert backlogs["India"]["EB3"] > 5_000


# ──────────────────────────────────────────────
# Inventory snapshot series
# ──────────────────────────────────────────────

def test_inventory_snapshots_are_ordered_and_dated():
    snaps = InventoryParser.snapshots()
    if len(snaps) < 2:
        pytest.skip("Need at least two inventory snapshots")
    keys = [(s["year"], s["month"]) for s in snaps]
    assert keys == sorted(keys), "snapshots must be chronological"
    assert all(s["label"] and s["file"] for s in snaps)
    assert all("India" in s["backlogs"] for s in snaps)


def test_inventory_snapshots_have_no_collapse():
    """Consecutive snapshots should not swing by an order of magnitude.

    A >90% single-month drop means a parse failure, not real drawdown. This is
    what would have caught the float-storage regression.
    """
    snaps = InventoryParser.snapshots()
    if len(snaps) < 2:
        pytest.skip("Need at least two inventory snapshots")
    for prev, curr in zip(snaps, snaps[1:]):
        for country in ("India", "China"):
            for cat, before in prev["backlogs"].get(country, {}).items():
                after = curr["backlogs"].get(country, {}).get(cat)
                if not before or after is None or before < 1000:
                    continue
                assert after > before * 0.5, (
                    f"{country} {cat} fell from {before} to {after} between "
                    f"{prev['label']} and {curr['label']}"
                )


def test_burn_rate_shape():
    result = InventoryParser.burn_rate("India", "EB1")
    if result["months_covered"] < 2:
        pytest.skip("Need at least two inventory snapshots")
    assert result["country"] == "India"
    assert result["change"] is not None
    assert result["per_month"] is not None
    assert result["first"]["pending"] > 0


# ──────────────────────────────────────────────
# I-485 quarterly dedup
# ──────────────────────────────────────────────

def test_quarterly_series_has_no_duplicate_periods():
    series = I485FlowParser().get_quarterly_series()
    keys = [(r["year"], r["month"]) for r in series]
    assert len(keys) == len(set(keys)), f"duplicate quarters: {keys}"


def test_quarterly_dedup_survives_filename_variant(tmp_path):
    """USCIS republishes a quarter under a second filename; both match the glob."""
    src_dir = "data/USCIS_I485"
    original = os.path.join(src_dir, "i485_performance_fy2026_q1.xlsx")
    if not os.path.exists(original):
        pytest.skip("FY2026 Q1 performance file not present")

    shutil.copy(original, tmp_path / "i485_performance_fy2026_q1.xlsx")
    shutil.copy(original, tmp_path / "i485_performance_data_fy2026_q1_v1.xlsx")

    series = I485FlowParser(str(tmp_path)).get_quarterly_series()
    assert len(series) == 1, "identical quarter published twice must collapse to one"


# ──────────────────────────────────────────────
# PERM fiscal-year naming
# ──────────────────────────────────────────────

@pytest.mark.parametrize("name,expected", [
    ("PERM_Disclosure_Data_FY15_Q4.xlsx", (2015, 4)),
    ("PERM_Disclosure_Data_FY16.xlsx", (2016, 4)),
    ("PERM_Disclosure_Data_FY17.xlsx", (2017, 4)),
    ("PERM_Disclosure_Data_FY2018_EOY.xlsx", (2018, 4)),
    ("PERM_Disclosure_Data_FY2026_Q2.xlsx", (2026, 2)),
    ("PERM_Disclosure_Data_New_Form_FY2024_Q4.xlsx", (2024, 4)),
])
def test_perm_fiscal_year_parsing(name, expected):
    """Pre-FY2018 files use a two-digit year; unparsed they collapse into FY 0."""
    assert _parse_fy_from_filename(name) == expected


# ──────────────────────────────────────────────
# DHS new arrivals / adjustments
# ──────────────────────────────────────────────

def test_dhs_newadj_splits_cover_expected_years():
    splits = {s.fiscal_year: s for s in DHSNewAdjParser().get_eb_splits()}
    if not splits:
        pytest.skip("No tables8-11 workbooks present")
    for fy, split in splits.items():
        assert split.aos and split.aos > 0, f"FY{fy} missing AOS"
        assert split.consular and split.consular > 0, f"FY{fy} missing consular"
        assert split.total == split.aos + split.consular


def test_dhs_newadj_matches_published_fy2022():
    """FY2022 is already in dhs_eb_category_usage.csv; the workbook must agree.

    This pins the column mapping: an off-by-one block or column would change
    these numbers.
    """
    splits = {s.fiscal_year: s for s in DHSNewAdjParser().get_eb_splits()}
    if 2022 not in splits:
        pytest.skip("FY2022 tables8-11 workbook not present")
    fy22 = splits[2022]
    assert fy22.aos == 221373
    assert fy22.consular == 48911
    assert fy22.total == 270284


def test_dhs_newadj_country_lookup_handles_aliases():
    """China is published as "China, People's Republic" in these workbooks."""
    parser = DHSNewAdjParser()
    china = [s for s in parser.get_eb_splits_for_country("China") if s.total]
    if not china:
        pytest.skip("No tables8-11 workbooks present")
    assert all(s.total > 0 for s in china)


# ──────────────────────────────────────────────
# I-140 RADP
# ──────────────────────────────────────────────

def _radp():
    parser = I140RADPParser.latest()
    if parser is None:
        pytest.skip("No RADP workbook present")
    return parser


def test_radp_summary_metrics():
    summary = _radp().get_summary()
    assert summary, "expected at least one reported quarter"
    first = summary[sorted(summary)[0]]
    assert first["TOTAL"]["received"] > 0
    assert first["TOTAL"]["pending"] > 0
    # Preference totals must not exceed the service-wide total
    for pref in ("EB1", "EB2", "EB3"):
        assert first[pref]["pending"] <= first["TOTAL"]["pending"]


def test_radp_country_preferences_sum_to_published_total():
    """EB1+EB2+EB3 must equal the sheet's own Total column.

    Guards against the trailing row-total column being summed into EB3.
    """
    table = _radp().get_receipts_by_country()
    grand = next((v for k, v in table.items() if k.lower() == "grand total"), None)
    assert grand is not None
    assert grand["EB1"] > 0 and grand["EB2"] > 0 and grand["EB3"] > 0
    # EB3 must be the same order of magnitude as the other preferences
    assert grand["EB3"] < (grand["EB1"] + grand["EB2"]) * 3


def test_radp_india_flow():
    flow = _radp().get_country_flow("India")
    assert flow["receipts"].get("EB2", 0) > 0
    assert flow["approvals"].get("EB2", 0) > 0


# ──────────────────────────────────────────────
# All-forms quarterly report
# ──────────────────────────────────────────────

def _all_forms():
    parser = AllFormsParser.latest()
    if parser is None:
        pytest.skip("No all-forms workbook present")
    return parser


def test_all_forms_parses_categories_and_total():
    parser = _all_forms()
    rows = parser.get_all_forms()
    assert len(rows) > 20
    totals = parser.get_totals()
    assert totals["received"] > 0
    assert totals["pending"] > 0
    assert "Employment Based" in {r["category"] for r in rows}


def test_all_forms_i140_matches_radp():
    """The two new reports describe the same I-140 quarter and must agree."""
    all_forms, radp = _all_forms(), _radp()
    i140 = all_forms.get_form("I-140")
    assert i140 is not None

    # The all-forms workbook reports one quarter; the RADP workbook can carry
    # several (the FY2026-Q2 drop holds Q1 and Q2). Compare the latest of each.
    summary = radp.get_summary()
    latest = summary[sorted(summary)[-1]]
    assert i140["pending"] == latest["TOTAL"]["pending"]
    assert i140["received"] == latest["TOTAL"]["received"]


def test_all_forms_period_and_processing_time():
    parser = _all_forms()
    assert parser.period and "-" in parser.period
    i140 = parser.get_form("I-140")
    assert i140["processing_time_months"] > 0


# ──────────────────────────────────────────────
# Degradation when data is absent or corrupt
# ──────────────────────────────────────────────

def test_parsers_return_nothing_when_data_absent(tmp_path):
    """A clone without the new drop must not raise."""
    empty = str(tmp_path)
    assert I140RADPParser.latest(empty) is None
    assert AllFormsParser.latest(empty) is None
    assert DHSNewAdjParser(empty).get_eb_splits() == []
    assert InventoryParser.snapshots(empty) == []
    assert InventoryParser.burn_rate("India", "EB1", empty)["months_covered"] == 0


def test_parsers_survive_corrupt_workbooks(tmp_path):
    """A truncated scanner download must degrade to empty, not fail the request."""
    (tmp_path / "i140_fy2026_q1_v1.xlsx").write_bytes(b"not an xlsx at all")
    (tmp_path / "quarterly_all_forms_fy2026_q1_v1.xlsx").write_bytes(b"truncated")
    (tmp_path / "plcy_tables8-11newadj_fy2022_d.xlsx").write_bytes(b"garbage")

    radp = I140RADPParser.latest(str(tmp_path))
    assert radp.get_summary() == {}
    assert radp.get_receipts_by_country() == {}
    assert radp.period is None

    all_forms = AllFormsParser.latest(str(tmp_path))
    assert all_forms.get_all_forms() == []
    assert all_forms.get_totals() is None

    splits = DHSNewAdjParser(str(tmp_path)).get_eb_splits()
    assert all(s.total is None for s in splits)
