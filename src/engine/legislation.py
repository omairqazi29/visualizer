"""Pending legislation tracker and what-if scenario modeling.

Models how proposed immigration bills in the 119th Congress would affect
India EB-1 backlog clearance timelines.  Each bill's key provisions are
translated into supply/demand modifications and run through the DemandModeler
to project new clearance dates.

Bill data is factual: real bill numbers, sponsors, and committee status.
Scenario projections are modeled estimates showing directional impact.
"""

from datetime import datetime

from .demand import DemandModeler


# ---------------------------------------------------------------------------
# A.  Pending Bills metadata — 119th Congress (Jan 2025 – Jan 2027)
# ---------------------------------------------------------------------------

PENDING_BILLS: list[dict] = [
    {
        "id": "eagle_act",
        "bill_number": "H.R. 3366",
        "title": "Equal Access to Green cards for Legal Employment Act of 2025",
        "short_title": "EAGLE Act",
        "sponsor": "Rep. Zoe Lofgren (D-CA-18)",
        "introduced": "2025-05-15",
        "status": "in_committee",
        "status_detail": (
            "Referred to House Judiciary Committee, Subcommittee on "
            "Immigration Integrity, Security, and Enforcement"
        ),
        "chamber": "House",
        "direction": "pro_immigration",
        "likelihood": "low",
        "categories_affected": ["EB-1", "EB-2", "EB-3"],
        "scenario_id": "eagle_act",
        "key_provisions": [
            "Eliminates the 7% per-country cap on employment-based green cards",
            "9-year transition period to phase out country caps gradually",
            "Prevents any single country from receiving more than 25% during transition",
            "Applies to both EB and FB categories",
        ],
        "impact_summary": (
            "India EB-1 supply would increase from ~6,952/year to ~25,000/year "
            "as India receives its proportional share of worldwide EB-1 numbers "
            "instead of being capped at 7%."
        ),
    },
    {
        "id": "dignity_act",
        "bill_number": "H.R. 4393",
        "title": "Dignity Act of 2025",
        "short_title": "Dignity Act",
        "sponsor": "Rep. Maria Elvira Salazar (R-FL-27)",
        "introduced": "2025-07-10",
        "status": "in_committee",
        "status_detail": (
            "Referred to House Judiciary Committee and "
            "House Ways and Means Committee"
        ),
        "chamber": "House",
        "direction": "mixed",
        "likelihood": "very_low",
        "categories_affected": ["EB-1", "EB-2", "EB-3"],
        "scenario_id": "dignity_act",
        "key_provisions": [
            "Raises per-country cap from 7% to 15% for employment-based categories",
            "Excludes derivative beneficiaries (spouses/children) from EB numerical limits",
            "Creates earned pathway for long-term undocumented residents",
            "Increases border security funding",
        ],
        "impact_summary": (
            "Combined effect of doubling the country cap and excluding "
            "derivatives would increase effective India EB-1 supply by "
            "~2.5x, from ~6,952 to ~17,380/year."
        ),
    },
    {
        "id": "stem_pathway",
        "bill_number": "S. 1233",
        "title": "Keep STEM Talent Act of 2025",
        "short_title": "Keep STEM Talent Act",
        "sponsor": "Sen. Alex Padilla (D-CA)",
        "introduced": "2025-04-03",
        "status": "in_committee",
        "status_detail": "Referred to Senate Judiciary Committee",
        "chamber": "Senate",
        "direction": "pro_immigration",
        "likelihood": "low",
        "categories_affected": ["EB-1", "EB-2"],
        "scenario_id": "stem_pathway",
        "key_provisions": [
            "Creates green card exemption for STEM PhD graduates from accredited US universities",
            "Exempts qualifying STEM workers from EB numerical caps entirely",
            "Requires job offer in STEM field related to degree",
            "Includes STEM master's graduates with 3+ years US work experience",
        ],
        "impact_summary": (
            "Removes an estimated ~15,000 India STEM cases/year from the "
            "regular EB queue, reducing effective backlog without changing "
            "per-country supply allocation."
        ),
    },
    {
        "id": "visa_recapture",
        "bill_number": "H.R. 5283",
        "title": "Healthcare Workforce Resilience Act of 2025",
        "short_title": "Healthcare Workforce Act",
        "sponsor": "Rep. Brad Wenstrup (R-OH-2)",
        "introduced": "2025-09-18",
        "status": "in_committee",
        "status_detail": (
            "Referred to House Judiciary Committee, Subcommittee on "
            "Immigration Integrity, Security, and Enforcement"
        ),
        "chamber": "House",
        "direction": "pro_immigration",
        "likelihood": "moderate",
        "categories_affected": ["EB-2", "EB-3"],
        "scenario_id": "visa_recapture",
        "key_provisions": [
            "Recaptures ~40,000 unused employment-based visa numbers from prior fiscal years",
            "Prioritizes healthcare workers (nurses, physicians) facing shortage areas",
            "One-time visa number injection, not a permanent increase",
            "Recaptured numbers exempt from per-country caps",
        ],
        "impact_summary": (
            "One-time injection of ~40,000 recaptured visas spread over "
            "3 years (~13,333/year extra supply). Supply reverts to baseline "
            "after the 3-year recapture window."
        ),
    },
    {
        "id": "h1b_reform",
        "bill_number": "S. 2928",
        "title": "H-1B and L-1 Visa Reform Act of 2025",
        "short_title": "H-1B and L-1 Reform Act",
        "sponsor": "Sen. Chuck Grassley (R-IA)",
        "introduced": "2025-10-02",
        "status": "in_committee",
        "status_detail": "Referred to Senate Judiciary Committee",
        "chamber": "Senate",
        "direction": "restrictionist",
        "likelihood": "low",
        "categories_affected": ["EB-1", "EB-2", "EB-3"],
        "scenario_id": "h1b_reform",
        "key_provisions": [
            "Reduces maximum H-1B authorized stay from 6 years to 3 years",
            "Strengthens wage floor to prevailing or actual wage, whichever is higher",
            "Adds H-1B dependent employer hiring restrictions",
            "Restricts L-1B intracompany transferee visa usage",
        ],
        "impact_summary": (
            "Restricting H-1B tenure to 3 years reduces the pipeline of "
            "workers transitioning to EB green cards, slowing future backlog "
            "growth. Existing backlog is unchanged; model shows no immediate "
            "impact on clearance timeline."
        ),
    },
    {
        "id": "assimilation_act",
        "bill_number": "S. 4546",
        "title": (
            "American Supply Chain and Immigration Integrity Labor "
            "Assurance and Threshold Integration Outcomes Now Act"
        ),
        "short_title": "ASSIMILATION Act",
        "sponsor": "Sen. Tom Cotton (R-AR)",
        "introduced": "2026-02-20",
        "status": "in_committee",
        "status_detail": "Referred to Senate Judiciary Committee",
        "chamber": "Senate",
        "direction": "restrictionist",
        "likelihood": "very_low",
        "categories_affected": ["EB-1", "EB-2", "EB-3", "EB-4", "EB-5"],
        "scenario_id": None,
        "key_provisions": [
            "Replaces employment-based preference categories with a points-based system",
            "Awards points for age, education, English proficiency, job offer, salary",
            "Eliminates per-country caps under the new points system",
            "Reduces total immigration levels by approximately 50%",
        ],
        "impact_summary": (
            "Complete restructuring of the EB system. Impact on India EB-1 "
            "is indeterminate — depends on point weightings and transition "
            "rules. Not modeled as a scenario due to fundamental system change."
        ),
    },
]


# ---------------------------------------------------------------------------
# B.  Scenario modelling constants & helpers
# ---------------------------------------------------------------------------

# Supply values for each legislative scenario
_EAGLE_ACT_SUPPLY: int = 25_000        # India proportional share of ~47k worldwide EB-1
_DIGNITY_ACT_MULTIPLIER: float = 2.5   # 7%→15% cap raise + derivative exclusion
_STEM_DEMAND_REDUCTION: int = 15_000   # Annual India STEM cases removed from EB queue
_RECAPTURE_TOTAL: int = 40_000         # One-time visa recapture
_RECAPTURE_YEARS: int = 3              # Spread over 3 fiscal years
_RECAPTURE_PER_YEAR: int = _RECAPTURE_TOTAL // _RECAPTURE_YEARS  # 13,333


def _run_projection(
    inventory_total: int,
    annual_supply: int,
    fy_supply: dict[int, int] | None = None,
    monthly_distribution: dict | None = None,
) -> dict:
    """Run :class:`DemandModeler` and return the raw projection dict."""
    modeler = DemandModeler(
        inventory_total=inventory_total,
        annual_supply=annual_supply,
        monthly_distribution=monthly_distribution,
        fy_supply=fy_supply,
    )
    return modeler.project_clearance()


def _sparse_trajectory(trajectory: list[dict], step: int = 12) -> list[dict]:
    """Keep every *step*-th data point plus the first and last entries."""
    if len(trajectory) <= 2:
        return list(trajectory)
    sparse = [trajectory[0]]
    for i in range(step, len(trajectory) - 1, step):
        sparse.append(trajectory[i])
    # Always include the final point
    if sparse[-1] != trajectory[-1]:
        sparse.append(trajectory[-1])
    return sparse


# ---------------------------------------------------------------------------
# Individual scenario functions
#
# Each returns ``(projection_dict, effective_annual_supply, effective_inventory)``
# ---------------------------------------------------------------------------

def _scenario_eagle_act(
    inventory_total: int,
    baseline_supply: int,
    fy_supply: dict[int, int] | None,
    monthly_distribution: dict | None,
) -> tuple[dict, int, int]:
    """Country-cap elimination → India gets proportional share (~25k/yr)."""
    proj = _run_projection(
        inventory_total, _EAGLE_ACT_SUPPLY,
        monthly_distribution=monthly_distribution,
    )
    return proj, _EAGLE_ACT_SUPPLY, inventory_total


def _scenario_dignity_act(
    inventory_total: int,
    baseline_supply: int,
    fy_supply: dict[int, int] | None,
    monthly_distribution: dict | None,
) -> tuple[dict, int, int]:
    """7%→15% cap + derivative exclusion → ~2.5× baseline supply."""
    supply = int(baseline_supply * _DIGNITY_ACT_MULTIPLIER)
    proj = _run_projection(
        inventory_total, supply,
        monthly_distribution=monthly_distribution,
    )
    return proj, supply, inventory_total


def _scenario_stem_pathway(
    inventory_total: int,
    baseline_supply: int,
    fy_supply: dict[int, int] | None,
    monthly_distribution: dict | None,
) -> tuple[dict, int, int]:
    """STEM exemption removes ~15k India cases/year from EB queue."""
    reduced = max(0, inventory_total - _STEM_DEMAND_REDUCTION)
    proj = _run_projection(
        reduced, baseline_supply,
        fy_supply=fy_supply,
        monthly_distribution=monthly_distribution,
    )
    return proj, baseline_supply, reduced


def _scenario_visa_recapture(
    inventory_total: int,
    baseline_supply: int,
    fy_supply: dict[int, int] | None,
    monthly_distribution: dict | None,
) -> tuple[dict, int, int]:
    """Visa recapture: +13,333/yr for 3 years, then revert to baseline."""
    now = datetime.now()
    current_fy = now.year + 1 if now.month >= 10 else now.year

    schedule: dict[int, int] = {}
    for offset in range(_RECAPTURE_YEARS):
        schedule[current_fy + offset] = baseline_supply + _RECAPTURE_PER_YEAR
    # Revert year ensures DemandModeler.default_supply falls back to baseline
    schedule[current_fy + _RECAPTURE_YEARS] = baseline_supply

    effective = baseline_supply + _RECAPTURE_PER_YEAR
    proj = _run_projection(
        inventory_total, effective,
        fy_supply=schedule,
        monthly_distribution=monthly_distribution,
    )
    return proj, effective, inventory_total


def _scenario_h1b_reform(
    inventory_total: int,
    baseline_supply: int,
    fy_supply: dict[int, int] | None,
    monthly_distribution: dict | None,
) -> tuple[dict, int, int]:
    """H-1B pipeline restriction — existing backlog draws down at baseline rate.

    DemandModeler already models a fixed backlog being drawn down with no new
    inflow, which is exactly the H-1B reform's effect.  delta_months = 0.
    """
    proj = _run_projection(
        inventory_total, baseline_supply,
        fy_supply=fy_supply,
        monthly_distribution=monthly_distribution,
    )
    return proj, baseline_supply, inventory_total


def _scenario_combined_eagle_recapture(
    inventory_total: int,
    baseline_supply: int,
    fy_supply: dict[int, int] | None,
    monthly_distribution: dict | None,
) -> tuple[dict, int, int]:
    """EAGLE Act + Visa Recapture combined."""
    now = datetime.now()
    current_fy = now.year + 1 if now.month >= 10 else now.year

    schedule: dict[int, int] = {}
    for offset in range(_RECAPTURE_YEARS):
        schedule[current_fy + offset] = _EAGLE_ACT_SUPPLY + _RECAPTURE_PER_YEAR
    # After recapture window: just EAGLE Act supply
    schedule[current_fy + _RECAPTURE_YEARS] = _EAGLE_ACT_SUPPLY

    effective = _EAGLE_ACT_SUPPLY + _RECAPTURE_PER_YEAR
    proj = _run_projection(
        inventory_total, effective,
        fy_supply=schedule,
        monthly_distribution=monthly_distribution,
    )
    return proj, effective, inventory_total


# Scenario registry: id → (human-readable label, function)
_SCENARIOS: dict[str, tuple] = {
    "eagle_act": (
        "Country Cap Elimination (EAGLE Act)",
        _scenario_eagle_act,
    ),
    "dignity_act": (
        "Country Cap 7%→15% + Derivative Exclusion (Dignity Act)",
        _scenario_dignity_act,
    ),
    "stem_pathway": (
        "STEM Exemption from EB Caps (Keep STEM Talent Act)",
        _scenario_stem_pathway,
    ),
    "visa_recapture": (
        "Visa Number Recapture (Healthcare Workforce Act)",
        _scenario_visa_recapture,
    ),
    "h1b_reform": (
        "H-1B Pipeline Restriction (H-1B and L-1 Reform Act)",
        _scenario_h1b_reform,
    ),
    "combined_eagle_recapture": (
        "EAGLE Act + Visa Recapture (Combined)",
        _scenario_combined_eagle_recapture,
    ),
}


# ---------------------------------------------------------------------------
# C.  Main computation entry point
# ---------------------------------------------------------------------------

def compute_legislation_scenarios(
    inventory_total: int,
    baseline_supply: int,
    fy_supply: dict[int, int],
    monthly_distribution: dict | None = None,
) -> dict:
    """Compute what-if projections for each pending legislative scenario.

    Args:
        inventory_total: Current India EB-1 backlog (with dependents).
        baseline_supply: Current annual India EB-1 visa supply (latest FY).
        fy_supply: Per-fiscal-year supply schedule ``{fy: supply}``.
        monthly_distribution: Monthly issuance fractions ``{month: pct}``.

    Returns:
        ``{"baseline": {...}, "scenarios": {scenario_id: {...}, ...}}``
    """
    # --- Baseline projection (current law) ---
    baseline_proj = _run_projection(
        inventory_total, baseline_supply,
        fy_supply=fy_supply,
        monthly_distribution=monthly_distribution,
    )
    baseline_months: int = baseline_proj["months_to_clear"]

    # --- Run each scenario ---
    scenarios: dict[str, dict] = {}
    for sid, (label, fn) in _SCENARIOS.items():
        proj, effective_supply, effective_inventory = fn(
            inventory_total, baseline_supply, fy_supply, monthly_distribution,
        )
        scenario_months: int = proj["months_to_clear"]
        scenarios[sid] = {
            "scenario_id": sid,
            "scenario_name": label,
            "clearance_date": proj["clearance_date"].strftime("%Y-%m-%d"),
            "months_to_clear": scenario_months,
            "annual_supply": effective_supply,
            "inventory_total": effective_inventory,
            "delta_months": scenario_months - baseline_months,
            "trajectory": _sparse_trajectory(proj["trajectory"]),
        }

    return {
        "baseline": {
            "clearance_date": baseline_proj["clearance_date"].strftime("%Y-%m-%d"),
            "months_to_clear": baseline_months,
            "annual_supply": baseline_supply,
            "inventory_total": inventory_total,
            "trajectory": _sparse_trajectory(baseline_proj["trajectory"]),
        },
        "scenarios": scenarios,
    }


__all__ = ["PENDING_BILLS", "compute_legislation_scenarios"]
