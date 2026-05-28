"""Centralized constants for The Spillover Engine.

All statutory limits, shares, and multipliers are defined here per INA 201/203
and the project's modeling assumptions.
"""

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

# INA 202(a)(2) per-country cap (7% of category limit)
PER_COUNTRY_CAP: float = 0.07

# Dependent multiplier per project mandate (I-140/I-485 primary + 2.2x dependents)
DEPENDENT_MULTIPLIER: float = 2.2

# Default monthly inflow of new India EB-1 I-140 approvals (primary petitions only).
# Based on FY2025 USCIS quarterly performance data (~500-600/month).
# Multiply by DEPENDENT_MULTIPLIER (2.2x) to get total persons added to backlog per month.
DEFAULT_MONTHLY_INFLOW: int = 550

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

# Default restricted countries for the 75-Country Freeze (hypothetical "Restriction Scenario").
# NOTE: Research (INA 201/203, 2026 Visa Bulletins) shows no enacted broad 75-country IV freeze.
# This models "what-if" demand reduction on high-FB/EB4-5 users to generate spillovers to EB-1.
# India deliberately excluded: it is the primary beneficiary of modeled surplus redistribution.
# Sources: travel.state.gov Visa Bulletins (India EB-1 FA 01APR23 as of May 2026), INA 202(a)(5) surplus rules.
DEFAULT_RESTRICTED_COUNTRIES: set[str] = {
    "Dominican Republic",
    "Philippines",
    "Bangladesh",
    "Vietnam",
    "Mexico",
    "China - mainland born",
}

# Actual countries subject to real immigrant visa entry suspensions / restrictions
# under 2025-2026 Presidential Proclamations and DOS public-benefits pause (distinct
# from hypothetical 75-country freeze). India and China-mainland explicitly NOT
# restricted. These generate limited but real additional EB-1 spillover via reduced
# FB/EB4-5 usage from listed countries.
# Sources (mid-2026):
# - https://www.whitehouse.gov/presidential-actions/2025/06/restricting-the-entry-of-foreign-nationals-to-protect-the-united-states-from-foreign-terrorists-and-other-national-security-and-public-safety-threats/
# - https://www.whitehouse.gov/presidential-actions/2025/12/restricting-and-limiting-the-entry-of-foreign-nationals-to-protect-the-security-of-the-united-states/
# - https://travel.state.gov/content/travel/en/News/visas-news/suspension-of-visa-issuance-to-foreign-nationals-to-protect-the-security-of-the-united-states.html
# - https://travel.state.gov/content/travel/en/News/visas-news/immigrant-visa-processing-updates-for-nationalities-at-high-risk-of-public-benefits-usage.html
ACTUAL_RESTRICTED_COUNTRIES: set[str] = {
    "Haiti",
    "Nigeria",
    "Venezuela",
    "Cuba",
    "Iran",
    "Somalia",
    "Sudan",
    "Afghanistan",
    "Syria",
    "Libya",
    "Yemen",
    "Burma",
    "Laos",
    "Eritrea",
    "Chad",
    "Mali",
    "Niger",
    "Burkina Faso",
}

# EB-4/EB-5 visa categories that spill over to EB-1 (per INA 203(b)).
# Centralized to avoid duplication across supply calc paths (standard, freeze, real_restrictions).
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
    "EB45_CATEGORIES",
    "DEFAULT_MONTHLY_INFLOW",
]
