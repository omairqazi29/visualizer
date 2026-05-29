"""Domain value objects for The Spillover Engine.

Pure data definitions — no I/O, no pandas, no imports from src/engine/ or src/parsers/.
These will be reconciled with the engine-layer SupplyBreakdown in a later PR.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import NewType, Literal, Optional
from enum import Enum


Chargeability = NewType("Chargeability", str)

VisaCategory = Literal[
    "E11", "E12", "E13", "E1", "IB1", "IB2",
    "SD", "SE", "SI1", "SI2", "SI3", "SK", "SQ1", "SQ2", "SQ3", "SR", "SU", "SW",
    "C5", "I5", "R5", "T5",
    "F1", "F2A", "F2B", "F3", "F4", "FX",
]


class PolicyName(str, Enum):
    """Supported spillover policy names."""

    STANDARD = "standard"
    FREEZE = "freeze"
    REAL_RESTRICTIONS = "real_restrictions"


@dataclass(frozen=True)
class FiscalYear:
    """US federal fiscal year (Oct 1 – Sep 30).

    ``ending_year`` is the calendar year the FY ends in,
    e.g. FY 2025 runs Oct 2024 – Sep 2025 → ending_year = 2025.
    """

    ending_year: int

    @property
    def start_date(self) -> datetime:
        """First instant of this fiscal year (Oct 1 of prior calendar year)."""
        return datetime(self.ending_year - 1, 10, 1)

    @property
    def end_date(self) -> datetime:
        """Last instant of this fiscal year (Sep 30 of ending_year)."""
        return datetime(self.ending_year, 9, 30, 23, 59, 59)

    def __str__(self) -> str:
        return f"FY{self.ending_year}"


@dataclass(frozen=True)
class INALimit:
    """Statutory limits per INA 201/203 and project modeling assumptions.

    Defaults mirror src/constants.py values; tests validate they stay in sync.
    """

    fb_floor: int = 226000
    eb_base: int = 140000
    eb1_share: float = 0.286
    per_country_cap: float = 0.07
    dependent_multiplier: float = 2.2


@dataclass
class SupplyBreakdown:
    """Enhanced supply breakdown — backward-compatible field set with metadata.

    NOTE: This is the *domain* SupplyBreakdown.  The engine-layer
    ``src.engine.supply.SupplyBreakdown`` (8 core fields, no metadata) is the
    active one used by SupplyCalculator and api/main.py.  The two will be
    reconciled in a future PR once all consumers are migrated to the DI-based
    SupplyCalculator interface.

    Intentionally mutable (not frozen): the engine-layer SupplyBreakdown is also
    mutable, and reconciliation may use builder/factory patterns that assign
    fields incrementally.  The ``__post_init__`` guard catches invalid
    *construction*; post-construction mutation is the caller's responsibility.
    """

    eb_base_limit: int
    fb_spillover_std: int
    fb_savings_freeze: int
    eb45_spillover_std: int
    eb45_savings_freeze: int
    total_eb_supply: int
    eb1_supply: int
    india_eb1_supply: int
    policy_applied: PolicyName = PolicyName.STANDARD
    computed_at: datetime = field(default_factory=lambda: datetime.now(tz=timezone.utc))
    source_data_checksum: Optional[str] = None

    def __post_init__(self) -> None:
        if self.total_eb_supply < 0:
            raise ValueError("total_eb_supply cannot be negative")
        if self.eb1_supply < 0:
            raise ValueError("eb1_supply cannot be negative")
        if self.india_eb1_supply < 0:
            raise ValueError("india_eb1_supply cannot be negative")


@dataclass(frozen=True)
class BacklogSnapshot:
    """Point-in-time snapshot of a backlog queue (e.g. India EB-1 inventory)."""

    mountain: int
    valley: int
    total: int
    as_of: Optional[datetime] = None

    def __post_init__(self) -> None:
        if self.mountain < 0:
            raise ValueError("mountain cannot be negative")
        if self.valley < 0:
            raise ValueError("valley cannot be negative")
        if self.total < 0:
            raise ValueError("total cannot be negative")


@dataclass(frozen=True)
class IndiaEB1Queue:
    """Composite queue size for India EB-1: inventory + pipeline."""

    mountain: int
    valley: int
    total: int

    def __post_init__(self) -> None:
        if self.mountain < 0:
            raise ValueError("mountain cannot be negative")
        if self.valley < 0:
            raise ValueError("valley cannot be negative")
        if self.total < 0:
            raise ValueError("total cannot be negative")

    @property
    def pipeline_excess(self) -> int:
        """Cases in total beyond mountain + valley (pipeline not yet in inventory)."""
        return max(0, self.total - self.mountain - self.valley)
