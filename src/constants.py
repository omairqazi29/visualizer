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

# Historical baseline for India EB-1 annual supply under standard INA flow
# (share of EB-1 + typical surplus from EB-2/EB-3 underutilization by other countries).
# This is an empirical assumption used when not applying the 75-country freeze.
DEFAULT_INDIA_EB1_SUPPLY: int = 9000

# Default restricted countries for the 75-Country Freeze ("Trump Effect")
DEFAULT_RESTRICTED_COUNTRIES: set[str] = {
    "Dominican Republic",
    "Philippines",
    "Bangladesh",
    "Vietnam",
    "Mexico",
    "China - mainland born",
    "India",
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
]
