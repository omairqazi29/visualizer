"""Domain layer for The Spillover Engine.

Pure value objects, exceptions, protocols, and policy stubs.
No I/O, no pandas usage in value objects, no imports from engine/parsers/api.
"""

from .value_objects import (
    Chargeability,
    VisaCategory,
    PolicyName,
    FiscalYear,
    INALimit,
    SupplyBreakdown,
    BacklogSnapshot,
    IndiaEB1Queue,
)
from .exceptions import (
    SpilloverError,
    DataLoadError,
    InvalidPolicyError,
    MathInvariantViolation,
)
from .protocols import SpilloverPolicy, DOSDataLoader, Parser
from .policies import StandardPolicy, FreezePolicy, RealRestrictionsPolicy

__all__ = [
    # Value objects
    "Chargeability",
    "VisaCategory",
    "PolicyName",
    "FiscalYear",
    "INALimit",
    "SupplyBreakdown",
    "BacklogSnapshot",
    "IndiaEB1Queue",
    # Exceptions
    "SpilloverError",
    "DataLoadError",
    "InvalidPolicyError",
    "MathInvariantViolation",
    # Protocols
    "SpilloverPolicy",
    "DOSDataLoader",
    "Parser",
    # Policy stubs
    "StandardPolicy",
    "FreezePolicy",
    "RealRestrictionsPolicy",
]
