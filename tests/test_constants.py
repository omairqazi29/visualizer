"""Tests to ensure statutory constants match INA expectations."""

from src.constants import (
    FB_STATUTORY_LIMIT,
    EB_BASE_LIMIT,
    EB1_STATUTORY_SHARE,
    EB45_STATUTORY_SHARE,
    PER_COUNTRY_CAP,
    DEPENDENT_MULTIPLIER,
    DEFAULT_INDIA_EB1_SUPPLY,
    ACTUAL_RESTRICTED_COUNTRIES,
    PROCLAMATION_RESTRICTED_COUNTRIES,
    DOS_IV_PAUSE_COUNTRIES_2026,
    EB45_DEPENDENT_MULTIPLIER,
    get_data_driven_multipliers,
)


def test_fb_statutory_limit():
    # INA 201(c) floor for family-based preference
    assert FB_STATUTORY_LIMIT == 226000


def test_eb_base_limit():
    # INA 203(b) worldwide employment-based limit
    assert EB_BASE_LIMIT == 140000


def test_eb1_share():
    assert EB1_STATUTORY_SHARE == 0.286


def test_eb45_share():
    assert EB45_STATUTORY_SHARE == 0.142


def test_per_country_cap():
    assert PER_COUNTRY_CAP == 0.07


def test_dependent_multiplier():
    # DHS Yearbook Table 7: EB-1 ~1.5 derivatives per principal → 2.5 total
    # Only applied to I-140 pipeline (I-485 inventory already includes dependents)
    assert DEPENDENT_MULTIPLIER == 2.5


def test_default_india_eb1_supply():
    # Researched value from FY2024 Report of the Visa Office (actual India EB-1 issuances: 6952)
    assert DEFAULT_INDIA_EB1_SUPPLY == 6952
    assert DEFAULT_INDIA_EB1_SUPPLY > 0


def test_eb45_dependent_multiplier():
    # Updated from 1.5 to 2.35 based on DHS Yearbook Table 7 5-year average
    assert EB45_DEPENDENT_MULTIPLIER == 2.35


def test_data_driven_multipliers():
    """get_data_driven_multipliers returns multipliers from DHS Yearbook CSV."""
    mults = get_data_driven_multipliers()
    assert isinstance(mults, dict)
    assert len(mults) == 5
    for cat in ["EB1", "EB2", "EB3", "EB4", "EB5"]:
        assert cat in mults
        assert 1.0 < mults[cat] < 4.0, f"{cat} multiplier {mults[cat]} out of range"
    # EB-1 should be ~2.5 from FY2023 data
    assert 2.3 < mults["EB1"] < 2.6


def test_actual_restricted_countries():
    # Proclamations 10949 + 10998 only = 39 countries. The DOS 75-country public
    # charge IV pause was vacated Aug 21, 2026 (CLINIC v. Rubio) and is no longer
    # part of the current-policy set.
    assert isinstance(ACTUAL_RESTRICTED_COUNTRIES, set)
    assert len(ACTUAL_RESTRICTED_COUNTRIES) == 39
    assert ACTUAL_RESTRICTED_COUNTRIES == PROCLAMATION_RESTRICTED_COUNTRIES
    # Proclamation ban countries
    assert "Haiti" in ACTUAL_RESTRICTED_COUNTRIES
    assert "Nigeria" in ACTUAL_RESTRICTED_COUNTRIES
    assert "Venezuela" in ACTUAL_RESTRICTED_COUNTRIES
    # IV-pause-only countries must NOT be restricted post-vacatur
    for country in ("Brazil", "Pakistan", "Bangladesh", "Egypt"):
        assert country not in ACTUAL_RESTRICTED_COUNTRIES
    # Beneficiaries must never be on the list
    assert "India" not in ACTUAL_RESTRICTED_COUNTRIES
    assert "China - mainland born" not in ACTUAL_RESTRICTED_COUNTRIES
    # Major IV consumers NOT on any real restriction list
    assert "Philippines" not in ACTUAL_RESTRICTED_COUNTRIES
    assert "Mexico" not in ACTUAL_RESTRICTED_COUNTRIES


def test_vacated_iv_pause_list_kept_for_history():
    # Historical only: in force Jan 21 - Aug 21, 2026, so FY2026 DOS data reflects it.
    assert len(DOS_IV_PAUSE_COUNTRIES_2026) == 75
    assert "Brazil" in DOS_IV_PAUSE_COUNTRIES_2026
    assert "India" not in DOS_IV_PAUSE_COUNTRIES_2026
    # 23 countries appeared on both lists
    assert len(DOS_IV_PAUSE_COUNTRIES_2026 & PROCLAMATION_RESTRICTED_COUNTRIES) == 23
