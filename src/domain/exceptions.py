"""Domain exceptions for The Spillover Engine.

Hierarchy:
    SpilloverError
    ├── DataLoadError
    ├── InvalidPolicyError
    └── MathInvariantViolation
"""


class SpilloverError(Exception):
    """Base exception for all Spillover Engine domain errors."""


class DataLoadError(SpilloverError):
    """Raised when data cannot be loaded or parsed from a source."""


class InvalidPolicyError(SpilloverError):
    """Raised when an unknown or invalid policy name is requested."""


class MathInvariantViolation(SpilloverError):
    """Raised when a computed value violates a mathematical invariant (e.g. negative supply)."""
