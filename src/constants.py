"""Centralized constants for The Spillover Engine.

All statutory limits, shares, and multipliers are defined here per INA 201/203
and the project's modeling assumptions.
"""

import csv
from functools import lru_cache

# INA 201(c) Family-Based annual floor (used to compute EB spillover)
FB_STATUTORY_LIMIT: int = 226000

# INA 203(b) Employment-Based annual base limit
EB_BASE_LIMIT: int = 140000

# EB category statutory shares (summing to 1.0)
EB1_STATUTORY_SHARE: float = 0.286  # 28.6% for EB-1 (priority workers)
EB2_STATUTORY_SHARE: float = 0.286  # 28.6% for EB-2
EB3_STATUTORY_SHARE: float = 0.286  # 28.6% for EB-3
EB4_STATUTORY_SHARE: float = 0.071  # 7.1% for EB-4
EB5_STATUTORY_SHARE: float = 0.071  # 7.1% for EB-5

# Combined EB-4 + EB-5 share (used for spillover calculations)
EB45_STATUTORY_SHARE: float = 0.142

# India's share of marginal EB-1 supply among oversubscribed countries.
# Based on relative I-485 EB-1 backlogs: India ~48k vs China ~10k → ~83%.
# Conservative default 80%. Update when new USCIS inventory data available.
INDIA_OVERSUBSCRIBED_SHARE: float = 0.80

# INA 202(a)(2) per-country cap (7% of category limit)
PER_COUNTRY_CAP: float = 0.07

# Dependent multipliers for I-140 pipeline (primary-only data → total persons).
# Source: DHS Yearbook of Immigration Statistics, Table 7; CRS Report R46291.
# Each EB category has a different derivative rate based on historical data.
# NOTE: Only applied to I-140 pipeline. I-485 inventory already counts each
# person individually (principal + derivatives each file their own I-485).
# See USCIS Q&A: "Pending EB I-485 Inventory" — confirmed to include derivatives.
# Prefer get_data_driven_multipliers() for data-driven values; these are fallback defaults.
DEPENDENT_MULTIPLIER: float = 2.5            # EB-1 default (used as fallback)
EB1_DEPENDENT_MULTIPLIER: float = 2.5        # EB-1: ~1.5 derivatives per principal
EB2_DEPENDENT_MULTIPLIER: float = 2.0        # EB-2: ~1.0 derivative per principal
EB3_DEPENDENT_MULTIPLIER: float = 2.1        # EB-3: ~1.06 derivatives per principal
EB45_DEPENDENT_MULTIPLIER: float = 2.35      # EB-4/5: 5-year avg from DHS Table 7 (EB-4 ~2.35x, EB-5 ~2.55x)

# Researched baseline for India EB-1 annual supply under standard INA flow.
# Value derived from official FY2024 data: India received 6,952 EB-1 visas
# (out of 47,462 total worldwide EB-1 issuances). Updated from prior empirical 9000.
# NOTE: These researched baselines (6952 + restricted sets) are from the May 2026 snapshot;
# runtime inventory/pipeline numbers now come from auto-discovered files via data_discovery.
# Sources: Report of the Visa Office 2024, Table V (travel.state.gov),
# DOS Visa Bulletins FY2025-2026, and USCIS/DOS notes on full category utilization.
# NOTE: Real 2025-2026 Presidential Proclamations (see ACTUAL_RESTRICTED_COUNTRIES)
# have reduced demand from ~20+ countries, generating additional real spillover
# not fully reflected in FY2025 DOS data. Use apply_real_restrictions=True for
# current-policy projections.
DEFAULT_INDIA_EB1_SUPPLY: int = 6952

# Default restricted countries for the hypothetical "Maximum Restriction Scenario".
# This models "what-if" demand reduction on the LARGEST FB/EB4-5 consuming countries
# (Philippines, Mexico, Dominican Republic, Vietnam, China-mainland) that are NOT on
# any real restriction list. Combined with ACTUAL_RESTRICTED_COUNTRIES (91 real countries),
# this represents the most extreme supply scenario.
# India deliberately excluded: it is the primary beneficiary of modeled surplus redistribution.
DEFAULT_RESTRICTED_COUNTRIES: set[str] = {
    "Dominican Republic",
    "Philippines",
    "Bangladesh",
    "Vietnam",
    "Mexico",
    "China - mainland born",
}

# Countries whose consular immigrant visa issuance is currently paused or suspended.
# UNION of two overlapping real policies (India/China-mainland explicitly NOT on either):
#
# POLICY 1 — Presidential Proclamations 10949 (Jun 2025) + 10998 (Dec 2025):
#   39 countries with entry suspension (security/vetting). Full or partial IV ban.
#   Source: whitehouse.gov/presidential-actions, travel.state.gov visa news
#
# POLICY 2 — DOS 75-Country IV Pause (eff. Jan 21, 2026, still in effect Jun 2026):
#   75 countries with consular immigrant visa issuance paused (public charge risk).
#   Source: travel.state.gov → "Immigrant Visa Processing Updates for Nationalities
#   at High Risk of U.S. Public Benefits Reliance" (last updated Feb 2, 2026)
#   Lawsuit pending: CLINIC v. Rubio (1:26-cv-00858, S.D.N.Y.) — no nationwide
#   injunction as of Jun 2026.
#
# Union = 91 countries. Both policies halt consular IV issuances (= DOS data).
# 16 countries only on Proclamation ban (not IV pause): Angola, Benin, Burkina Faso,
#   Burundi, Chad, Equatorial Guinea, Gabon, Malawi, Mali, Mauritania, Niger, Tonga,
#   Turkmenistan, Venezuela, Zambia, Zimbabwe
# 52 countries only on IV pause (not Proclamation): Albania, Algeria, Armenia, ...
#   Brazil, Pakistan, Bangladesh, Egypt, Ethiopia, Colombia, Ghana, etc.
# 23 countries on BOTH lists.
#
# USCIS adjudicative hold (PM-602-0192/0194) for the 39 Proclamation countries was
# vacated nationwide Jun 5, 2026 (Dorcas v. USCIS). No model impact — savings are
# derived from DOS consular data, not domestic I-485 processing.
ACTUAL_RESTRICTED_COUNTRIES: set[str] = {
    # --- On BOTH Proclamation ban AND DOS IV pause ---
    "Afghanistan",
    "Antigua and Barbuda",
    "Burma",
    "Cote d'Ivoire",
    "Cuba",
    "Dominica",
    "Eritrea",
    "Gambia",
    "Haiti",
    "Iran",
    "Laos",
    "Libya",
    "Nigeria",
    "Republic of the Congo",
    "Senegal",
    "Sierra Leone",
    "Somalia",
    "South Sudan",
    "Sudan",
    "Syria",
    "Tanzania",
    "Togo",
    "Yemen",
    # --- Proclamation ban only (39-list, not on 75-country IV pause) ---
    "Angola",
    "Benin",
    "Burkina Faso",
    "Burundi",
    "Chad",
    "Equatorial Guinea",
    "Gabon",
    "Malawi",
    "Mali",
    "Mauritania",
    "Niger",
    "Tonga",
    "Turkmenistan",
    "Venezuela",
    "Zambia",
    "Zimbabwe",
    # --- DOS 75-country IV pause only (not on Proclamation ban) ---
    "Albania",
    "Algeria",
    "Armenia",
    "Azerbaijan",
    "Bahamas",
    "Bangladesh",
    "Barbados",
    "Belarus",
    "Belize",
    "Bhutan",
    "Bosnia and Herzegovina",
    "Brazil",
    "Cambodia",
    "Cameroon",
    "Cape Verde",
    "Colombia",
    "Democratic Republic of the Congo",
    "Egypt",
    "Ethiopia",
    "Fiji",
    "Georgia",
    "Ghana",
    "Grenada",
    "Guatemala",
    "Guinea",
    "Iraq",
    "Jamaica",
    "Jordan",
    "Kazakhstan",
    "Kosovo",
    "Kuwait",
    "Kyrgyz Republic",
    "Lebanon",
    "Liberia",
    "Moldova",
    "Mongolia",
    "Montenegro",
    "Morocco",
    "Nepal",
    "Nicaragua",
    "North Macedonia",
    "Pakistan",
    "Russia",
    "Rwanda",
    "Saint Kitts and Nevis",
    "Saint Lucia",
    "Saint Vincent and the Grenadines",
    "Thailand",
    "Tunisia",
    "Uganda",
    "Uruguay",
    "Uzbekistan",
}


# DOS visa symbol codes by EB preference category.
# Used to compute savings from restricted countries across ALL EB categories.
EB2_CATEGORIES: list[str] = ['E21', 'E22', 'E26', 'E27']
EB3_CATEGORIES: list[str] = ['E31', 'E32', 'E34', 'E36', 'E37', 'EW3', 'EW4', 'EW5']

# EB-4/EB-5 visa categories that spill over to EB-1 (per INA 203(b)).
EB45_CATEGORIES: list[str] = [
    "SD",
    "SE",
    "SI1",
    "SI2",
    "SI3",
    "SK",
    "SQ1",
    "SQ2",
    "SQ3",
    "SR",
    "SU",
    "SW",
    "C5",
    "I5",
    "R5",
    "T5",
]


@lru_cache(maxsize=1)
def get_data_driven_multipliers(csv_path: str = "data/DHS_Yearbook/dhs_table7_eb_multipliers.csv") -> dict[str, float]:
    """Load dependent multipliers from DHS Yearbook Table 7 data.

    Returns multipliers for the latest available fiscal year.
    Falls back to hardcoded constants if CSV is unavailable.

    Source: DHS Yearbook of Immigration Statistics, Table 7 —
    Persons Obtaining LPR Status by Type and Detailed Class of Admission.
    """
    try:
        with open(csv_path, newline="") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        if not rows:
            raise FileNotFoundError
        # Find latest fiscal year
        latest_fy = max(int(r["fiscal_year"]) for r in rows)
        latest = {r["category"]: float(r["multiplier"]) for r in rows if int(r["fiscal_year"]) == latest_fy}
        return latest
    except (FileNotFoundError, KeyError, ValueError):
        return {
            "EB1": EB1_DEPENDENT_MULTIPLIER,
            "EB2": EB2_DEPENDENT_MULTIPLIER,
            "EB3": EB3_DEPENDENT_MULTIPLIER,
            "EB4": EB45_DEPENDENT_MULTIPLIER,
            "EB5": EB45_DEPENDENT_MULTIPLIER,
        }


__all__ = [
    "FB_STATUTORY_LIMIT",
    "EB_BASE_LIMIT",
    "EB1_STATUTORY_SHARE",
    "EB2_STATUTORY_SHARE",
    "EB3_STATUTORY_SHARE",
    "EB4_STATUTORY_SHARE",
    "EB5_STATUTORY_SHARE",
    "EB45_STATUTORY_SHARE",
    "PER_COUNTRY_CAP",
    "DEPENDENT_MULTIPLIER",
    "DEFAULT_INDIA_EB1_SUPPLY",
    "DEFAULT_RESTRICTED_COUNTRIES",
    "ACTUAL_RESTRICTED_COUNTRIES",

    "EB2_CATEGORIES",
    "EB3_CATEGORIES",
    "EB45_CATEGORIES",
    "INDIA_OVERSUBSCRIBED_SHARE",
    "EB1_DEPENDENT_MULTIPLIER",
    "EB2_DEPENDENT_MULTIPLIER",
    "EB3_DEPENDENT_MULTIPLIER",
    "EB45_DEPENDENT_MULTIPLIER",
    "get_data_driven_multipliers",
]
