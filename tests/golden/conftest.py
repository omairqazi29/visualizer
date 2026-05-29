"""Golden test fixtures.

Provides skip-if-no-data markers and reference-loading helpers so that
golden tests degrade gracefully when data/ files are absent (e.g. in CI
without the xlsx corpus).
"""

import json
from pathlib import Path

import pytest

REFERENCES_DIR = Path(__file__).resolve().parent / "references"

_DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"
_HAS_DATA = (_DATA_DIR / "DOS").is_dir() and any((_DATA_DIR / "DOS").glob("*.xlsx"))

requires_data = pytest.mark.skipif(
    not _HAS_DATA,
    reason="Live data files not present (data/DOS/*.xlsx)",
)


@pytest.fixture
def golden_reference() -> dict:
    """Load the supply_breakdown.json reference, skip if missing."""
    ref_path = REFERENCES_DIR / "supply_breakdown.json"
    if not ref_path.exists():
        pytest.skip(f"Golden reference not found: {ref_path}")
    with open(ref_path) as f:
        return json.load(f)
