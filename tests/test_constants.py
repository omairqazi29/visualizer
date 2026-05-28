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
    DEFAULT_MONTHLY_INFLOW,
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
    assert DEPENDENT_MULTIPLIER == 2.2


def test_default_india_eb1_supply():
    # Researched value from FY2024 Report of the Visa Office (actual India EB-1 issuances: 6952)
    assert DEFAULT_INDIA_EB1_SUPPLY == 6952
    assert DEFAULT_INDIA_EB1_SUPPLY > 0


def test_default_monthly_inflow():
    # Based on FY2025 USCIS quarterly data (~500-600 primary I-140 approvals/month)
    assert DEFAULT_MONTHLY_INFLOW == 550
    assert DEFAULT_MONTHLY_INFLOW > 0


def test_actual_restricted_countries():
    # Real (not hypo) countries from 2025-2026 Proclamations; India/China excluded; used for accurate current-policy spillover
    assert isinstance(ACTUAL_RESTRICTED_COUNTRIES, set)
    assert len(ACTUAL_RESTRICTED_COUNTRIES) >= 10
    assert "Haiti" in ACTUAL_RESTRICTED_COUNTRIES
    assert "Nigeria" in ACTUAL_RESTRICTED_COUNTRIES
    assert "India" not in ACTUAL_RESTRICTED_COUNTRIES
    assert "China - mainland born" not in ACTUAL_RESTRICTED_COUNTRIES
