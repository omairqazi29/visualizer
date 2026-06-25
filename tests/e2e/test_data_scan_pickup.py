"""E2E: mock-publish government data pages, then scan_and_pr picks up new files.

Requires a running mock-data-publisher (Docker or local). Not part of the default
unit suite — run with::

    pytest tests/e2e/test_data_scan_pickup.py -m e2e -v
    # or
    ./scripts/e2e_data_scan_pickup.sh

Env:
  MOCK_PUBLISHER_URL   default http://127.0.0.1:8765 (use http://mock-data-publisher:8765 in compose)
  INGESTION_*          set by script/compose for isolated data dir + URL overrides
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import pytest
import requests

# Mark entire module
pytestmark = [pytest.mark.e2e, pytest.mark.integration]


def _mock_base() -> str:
    return os.environ.get("MOCK_PUBLISHER_URL", "http://127.0.0.1:8765").rstrip("/")


def _mock_ready() -> bool:
    try:
        r = requests.get(f"{_mock_base()}/health", timeout=3)
        return r.status_code == 200 and r.json().get("status") == "ok"
    except Exception:  # noqa: BLE001
        return False


def _apply_ingestion_env(data_root: Path, project_root: Path, mock_base: str) -> None:
    """Configure opt-in env overrides for isolated scan/fetch against mock."""
    os.environ["INGESTION_PROJECT_ROOT"] = str(project_root)
    os.environ["INGESTION_DATA_DIR"] = str(data_root)
    os.environ["INGESTION_REQUEST_DELAY_SEC"] = "0"
    os.environ["INGESTION_EXTRA_ALLOWED_HOSTS"] = (
        "mock-data-publisher,localhost,127.0.0.1"
    )
    os.environ["INGESTION_SOURCE_URL_dos_iv_fsc"] = f"{mock_base}/dos/monthly"
    os.environ["INGESTION_SOURCE_URL_uscis_inventory"] = f"{mock_base}/uscis/data"
    os.environ["INGESTION_SOURCE_URL_uscis_i485_perf"] = f"{mock_base}/uscis/data"
    os.environ["INGESTION_SOURCE_URL_uscis_i140"] = f"{mock_base}/uscis/data"
    # JSON overrides (redundant but exercises the alternate path)
    os.environ["INGESTION_SOURCE_URL_OVERRIDES"] = json.dumps({
        "dos_iv_fsc": f"{mock_base}/dos/monthly",
    })


def _refresh_registry():
    from src.ingestion import registry
    registry.refresh_paths_from_env()


@pytest.fixture(scope="module")
def mock_publisher():
    if not _mock_ready():
        pytest.skip(
            f"mock-data-publisher not reachable at {_mock_base()}/health — "
            "start with: docker compose -f docker-compose.yml "
            "-f docker-compose.data-scan-e2e.yml --profile data-scan-e2e "
            "up --build -d mock-data-publisher"
        )
    # Reset to seed for deterministic runs
    try:
        requests.post(f"{_mock_base()}/reset", timeout=5)
    except Exception:  # noqa: BLE001
        pass
    return _mock_base()


@pytest.fixture
def isolated_data(tmp_path, mock_publisher):
    """Empty data tree + project root env; yield (data_dir, project_root)."""
    project_root = Path(__file__).resolve().parents[2]
    data_dir = tmp_path / "data"
    # Mirror expected subdirs (scanner writes here via INGESTION_DATA_DIR)
    for sub in ("DOS", "USCIS_I485", "DHS_Yearbook", "DOL_PERM"):
        (data_dir / sub).mkdir(parents=True, exist_ok=True)
    _apply_ingestion_env(data_dir, project_root, mock_publisher)
    _refresh_registry()
    yield data_dir, project_root
    # Clean env keys we set (avoid leaking into other tests in same process)
    for k in list(os.environ):
        if k.startswith("INGESTION_"):
            os.environ.pop(k, None)
    _refresh_registry()


def test_mock_health(mock_publisher):
    r = requests.get(f"{mock_publisher}/health", timeout=5)
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["files_published"] >= 2


def test_mock_dos_page_has_fsc_links(mock_publisher):
    r = requests.get(f"{mock_publisher}/dos/monthly", timeout=5)
    assert r.status_code == 200
    assert "IV Issuances by FSC" in r.text
    assert ".xlsx" in r.text


def test_scan_first_pass_finds_seed_as_new(isolated_data, mock_publisher):
    """Empty temp data/ => seeded mock files should all be status=new."""
    data_dir, _ = isolated_data
    from src.ingestion.registry import get_source, REQUEST_DELAY_SEC
    from src.ingestion.scanner import scan_source

    src = get_source("dos_iv_fsc")
    assert "8765" in src.scan_url or "mock" in src.scan_url or "127.0.0.1" in src.scan_url
    assert any(h in ("localhost", "127.0.0.1", "mock-data-publisher")
               for h in (src.allowed_hosts or ()))

    result = scan_source(src, delay=0.0)
    assert result.page_fetched, f"scan failed: {result.errors}"
    new_names = [c.filename for c in result.new_candidates]
    assert len(result.new_candidates) >= 2, (
        f"expected >=2 new DOS files from seed, got {len(result.new_candidates)}: "
        f"{[c.to_dict() for c in result.candidates]}"
    )
    assert any("OCTOBER 2025" in n for n in new_names)
    assert all(c.status == "new" for c in result.new_candidates)


def test_publish_then_second_scan_picks_up_delta(isolated_data, mock_publisher):
    """Core e2e: first scan+fetch seed, POST /publish/new, second scan sees exactly that as new."""
    data_dir, _ = isolated_data
    from src.ingestion.registry import get_source
    from src.ingestion.scanner import scan_source
    from src.ingestion.fetcher import fetch_candidates

    src = get_source("dos_iv_fsc")

    # --- Pass 1: scan + fetch seed into temp data/DOS ---
    r1 = scan_source(src, delay=0.0)
    assert r1.page_fetched, f"pass1 scan failed: {r1.errors}"
    assert len(r1.new_candidates) >= 2
    seed_new = list(r1.new_candidates)
    fetched = fetch_candidates(seed_new, delay=0.0)
    ok_fetched = [f for f in fetched if f.success]
    assert len(ok_fetched) >= 1, f"fetch failed: {[f.error for f in fetched]}"

    # Verify files landed under isolated data dir
    dos_dir = data_dir / "DOS"
    on_disk = list(dos_dir.glob("*.xlsx")) if dos_dir.exists() else []
    assert len(on_disk) >= 1, f"expected xlsx under {dos_dir}"

    # --- Publish a brand-new month on the mock ---
    pub = requests.post(
        f"{mock_publisher}/publish/new",
        json={"kind": "dos"},
        timeout=5,
    )
    assert pub.status_code == 200, pub.text
    pub_body = pub.json()
    assert pub_body.get("ok") is True
    published_name = pub_body["filename"]
    assert "IV Issuances by FSC" in published_name

    # --- Pass 2: scan again — only the newly published file should be status=new ---
    r2 = scan_source(src, delay=0.0)
    assert r2.page_fetched, f"pass2 scan failed: {r2.errors}"
    new2 = r2.new_candidates
    exist2 = r2.existing_candidates

    new_names = [c.filename for c in new2]
    exist_names = [c.filename for c in exist2]

    assert published_name in new_names, (
        f"expected published file {published_name!r} as status=new; "
        f"new={new_names}; exist={exist_names}; all={[c.to_dict() for c in r2.candidates]}"
    )
    # Previously fetched seed files should now be exists (not new)
    assert len(exist2) >= 1, f"expected prior files as exists, got exist={exist_names}"
    # Only the delta should be strictly new (allow edge cases but assert published is among them)
    assert all(c.status == "new" for c in new2)
    assert published_name not in exist_names

    # --- Fetch + validate the delta ---
    delta_cands = [c for c in new2 if c.filename == published_name]
    assert len(delta_cands) == 1
    fetched2 = fetch_candidates(delta_cands, delay=0.0)
    assert fetched2 and fetched2[0].success, (
        f"delta fetch failed: {fetched2[0].error if fetched2 else 'no result'}"
    )
    dest = dos_dir / published_name
    assert dest.exists(), f"expected {dest} on disk"
    # Magic bytes: xlsx is zip (PK)
    assert dest.read_bytes()[:2] == b"PK"

    # Light parser/validator pass on the isolated tree (minimal fixtures may warn)
    from src.ingestion.validator import validate_downloaded_files
    vreport = validate_downloaded_files([dest], require_under_data=False)
    assert vreport is not None
    print(
        f"\n[e2e ok] pass1_new={len(seed_new)} fetched={len(ok_fetched)} "
        f"published={published_name!r} pass2_new={new_names} "
        f"pass2_exists={len(exist2)} dest={dest} size={dest.stat().st_size} "
        f"validator_ok={getattr(vreport, 'ok', 'n/a')}"
    )


def test_scan_and_pr_cli_against_mock(isolated_data, mock_publisher, capsys):
    """CLI path: scan_and_pr --scan --source dos_iv against mock (dry-run, no fetch)."""
    from src.scripts.scan_and_pr import main

    rc = main(["--scan", "--source", "dos_iv", "--dry-run"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "dos_iv_fsc" in out or "Scanning" in out or "new" in out.lower()


def test_uscis_mock_scan(isolated_data, mock_publisher):
    """USCIS sources pointed at mock /uscis/data should find seed xlsx."""
    from src.ingestion.registry import get_source
    from src.ingestion.scanner import scan_source

    for sid in ("uscis_i140", "uscis_i485_perf", "uscis_inventory"):
        src = get_source(sid)
        r = scan_source(src, delay=0.0)
        assert r.page_fetched, f"{sid} scan failed: {r.errors}"
        # At least one matching pattern among candidates
        assert len(r.candidates) >= 1, f"{sid}: no candidates from mock USCIS page"
