"""Automated pytest wrapper for golden reference verification.

Ensures golden verify runs as part of the regular ``pytest`` suite when
both reference JSON and live data files are available.
"""

from tests.golden.conftest import requires_data, requires_reference


@requires_data
@requires_reference
def test_golden_verify_passes():
    """Golden verify_against_reference() succeeds against current engine."""
    from tests.golden.capture_and_verify import verify_against_reference

    assert verify_against_reference() is True
