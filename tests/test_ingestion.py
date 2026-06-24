"""Unit tests for data ingestion scanner/fetcher/registry (mocked HTTP, no live network)."""

from __future__ import annotations

import textwrap
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.ingestion.registry import (
    SOURCE_REGISTRY,
    get_source,
    list_sources,
    resolve_source_ids,
    target_path_for,
    _dos_dedup_key,
    _normalize_dos_fsc_name,
    _normalize_uscis_name,
)
from src.ingestion.scanner import (
    RemoteCandidate,
    extract_links,
    scan_source,
    scan_sources,
)
from src.ingestion.fetcher import fetch_candidate, fetch_candidates
from src.ingestion.pr_helper import build_pr_body, propose_branch_name, paths_from_fetch_results
from src.ingestion.fetcher import FetchResult


# ── Registry ────────────────────────────────────────────────────────────────


def test_registry_has_core_sources():
    for sid in (
        "dos_iv_fsc",
        "visa_bulletin",
        "uscis_inventory",
        "uscis_i485_perf",
        "uscis_i140",
        "dhs_yearbook",
        "dol_perm",
    ):
        assert sid in SOURCE_REGISTRY
        src = SOURCE_REGISTRY[sid]
        assert src.scan_url.startswith("http")
        assert src.target_dir.startswith("data")


def test_get_source_unknown_raises():
    with pytest.raises(KeyError):
        get_source("not_a_real_source")


def test_resolve_source_ids_groups():
    assert "dos_iv_fsc" in resolve_source_ids("dos_iv")
    assert "visa_bulletin" in resolve_source_ids("visa_bulletin")
    uscis = resolve_source_ids("uscis")
    assert "uscis_inventory" in uscis
    assert "uscis_i485_perf" in uscis
    assert "uscis_i140" in uscis
    all_ids = resolve_source_ids("all")
    assert "dos_iv_fsc" in all_ids
    # disabled sources excluded from all
    assert "uscis_landing" not in all_ids


def test_resolve_source_ids_comma_and_single():
    ids = resolve_source_ids("dos_iv,uscis_i140")
    assert ids == ["dos_iv_fsc", "uscis_i140"]
    assert resolve_source_ids("dos_iv_fsc") == ["dos_iv_fsc"]


def test_list_sources_enabled_only():
    enabled = list_sources(enabled_only=True)
    assert all(s.enabled for s in enabled)
    all_s = list_sources(enabled_only=False)
    assert len(all_s) >= len(enabled)


def test_filename_normalization():
    url = (
        "https://travel.state.gov/content/dam/visas/Statistics/Immigrant-Statistics/"
        "MonthlyIVIssuances/Excel/FY2025/OCTOBER%202024%20-%20IV%20Issuances%20by%20FSC"
        "%20or%20Place%20of%20Birth%20and%20Visa%20Class.xlsx"
    )
    name = _normalize_dos_fsc_name(url)
    assert "OCTOBER 2024" in name
    assert name.endswith(".xlsx")
    assert "%20" not in name

    uscis_url = (
        "https://www.uscis.gov/sites/default/files/document/reports/"
        "i485_performance_data_fy2026_q1_v1.xlsx"
    )
    assert _normalize_uscis_name(uscis_url) == "i485_performance_data_fy2026_q1_v1.xlsx"


def test_dos_dedup_key_strips_version_suffix():
    a = _dos_dedup_key(
        "DECEMBER 2022 - IV Issuances by FSC or Place of Birth and Visa Class_v1.xlsx"
    )
    b = _dos_dedup_key(
        "DECEMBER 2022 - IV Issuances by FSC or Place of Birth and Visa Class.xlsx"
    )
    assert a == b


def test_target_path_for():
    src = get_source("dos_iv_fsc")
    p = target_path_for(src, "JANUARY 2025 - IV Issuances by FSC or Place of Birth and Visa Class.xlsx")
    assert p.parts[-2] == "DOS"
    assert p.name.startswith("JANUARY")


# ── Link extraction ─────────────────────────────────────────────────────────


SAMPLE_DOS_HTML = textwrap.dedent(
    """
    <html><body>
    <a href="/content/dam/visas/Statistics/Immigrant-Statistics/MonthlyIVIssuances/Excel/FY2025/OCTOBER%202024%20-%20IV%20Issuances%20by%20FSC%20or%20Place%20of%20Birth%20and%20Visa%20Class.xlsx">Excel</a>
    <a href="/content/dam/visas/Statistics/Immigrant-Statistics/MonthlyIVIssuances/Excel/FY2025/OCTOBER%202024%20-%20IV%20Issuances%20by%20Post%20and%20Visa%20Class.xlsx">Excel</a>
    <a href="/content/dam/visas/Statistics/Immigrant-Statistics/MonthlyIVIssuances/Excel/FY2025/NOVEMBER%202024%20-%20IV%20Issuances%20by%20FSC%20or%20Place%20of%20Birth%20and%20Visa%20Class.xlsx">(Excel)</a>
    <a href="https://travel.state.gov/content/travel/en/legal/visa-law0/visa-bulletin.html">VB</a>
    </body></html>
    """
).strip()

SAMPLE_USCIS_HTML = textwrap.dedent(
    """
    <html><body>
    <a href="/sites/default/files/document/reports/eb_i140_i360_i526_performancedata_fy2026_q1_v1.xlsx">EB perf</a>
    <a href="/sites/default/files/document/reports/i140_rec_by_class_country_fy2026_q1_v1.xlsx">I-140 rec</a>
    <a href="/sites/default/files/document/reports/i485_performance_data_fy2026_q1_v1.xlsx">I-485 perf</a>
    <a href="/sites/default/files/document/reports/n400_performance_data_fy2026_q1_v1.xlsx">N-400</a>
    <a href="/sites/default/files/document/reports/eb_inventory_april_2026.xlsx">EB inventory</a>
    </body></html>
    """
).strip()

SAMPLE_VB_HTML = textwrap.dedent(
    """
    <html><body>
    <a href="/content/travel/en/legal/visa-law0/visa-bulletin/2026/visa-bulletin-for-june-2026.html">June 2026</a>
    <a href="/content/travel/en/legal/visa-law0/visa-bulletin/2026/visa-bulletin-for-july-2026.html">July 2026</a>
    <a href="/content/travel/en/legal/visa-law0/visa-bulletin.html">Index</a>
    </body></html>
    """
).strip()


def test_extract_links_absolute_and_relative():
    base = "https://travel.state.gov/content/travel/en/legal/page.html"
    links = extract_links(SAMPLE_DOS_HTML, base)
    assert len(links) >= 3
    urls = [u for u, _ in links]
    assert any("FSC" in u or "FSC" in unquote_safe(u) for u in urls)
    assert all(u.startswith("http") for u in urls)


def unquote_safe(u: str) -> str:
    from urllib.parse import unquote

    return unquote(u)


def test_scan_dos_fsc_filters_post_files_and_detects_new(tmp_path, monkeypatch):
    """Only FSC files match; Post files excluded. Existing local file marked exists."""
    src = get_source("dos_iv_fsc")
    # Point target_dir at temp by patching target_path_for / PROJECT_ROOT usage via monkeypatch on module
    dos_dir = tmp_path / "data" / "DOS"
    dos_dir.mkdir(parents=True)
    existing = (
        "OCTOBER 2024 - IV Issuances by FSC or Place of Birth and Visa Class.xlsx"
    )
    (dos_dir / existing).write_bytes(b"fake-xlsx")

    import src.ingestion.scanner as scanner_mod
    import src.ingestion.registry as reg_mod

    monkeypatch.setattr(reg_mod, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(scanner_mod, "PROJECT_ROOT", tmp_path)

    result = scan_source(src, html_override=SAMPLE_DOS_HTML, delay=0, dry_run=True)
    assert result.page_fetched
    assert result.errors == []
    # FSC only (2 in sample), not Post
    assert len(result.candidates) == 2
    names = {c.filename for c in result.candidates}
    assert any("OCTOBER 2024" in n and "FSC" in n for n in names)
    assert any("NOVEMBER 2024" in n and "FSC" in n for n in names)
    assert not any("Post" in n for n in names)

    oct_c = next(c for c in result.candidates if "OCTOBER 2024" in c.filename)
    nov_c = next(c for c in result.candidates if "NOVEMBER 2024" in c.filename)
    assert oct_c.status == "exists"
    assert nov_c.status == "new"


def test_scan_uscis_i140_patterns(tmp_path, monkeypatch):
    import src.ingestion.scanner as scanner_mod
    import src.ingestion.registry as reg_mod

    monkeypatch.setattr(reg_mod, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(scanner_mod, "PROJECT_ROOT", tmp_path)
    (tmp_path / "data").mkdir(parents=True)

    src = get_source("uscis_i140")
    result = scan_source(src, html_override=SAMPLE_USCIS_HTML, delay=0)
    fnames = [c.filename for c in result.candidates]
    assert any("eb_i140" in f for f in fnames)
    assert any("i140_rec" in f for f in fnames)
    # N-400 must not match i140 source
    assert not any("n400" in f for f in fnames)
    assert all(c.status == "new" for c in result.candidates)


def test_scan_uscis_i485_perf(tmp_path, monkeypatch):
    import src.ingestion.scanner as scanner_mod
    import src.ingestion.registry as reg_mod

    monkeypatch.setattr(reg_mod, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(scanner_mod, "PROJECT_ROOT", tmp_path)
    (tmp_path / "data" / "USCIS_I485").mkdir(parents=True)

    src = get_source("uscis_i485_perf")
    result = scan_source(src, html_override=SAMPLE_USCIS_HTML, delay=0)
    assert len(result.candidates) >= 1
    assert all("i485_performance" in c.filename for c in result.candidates)


def test_scan_uscis_inventory(tmp_path, monkeypatch):
    import src.ingestion.scanner as scanner_mod
    import src.ingestion.registry as reg_mod

    monkeypatch.setattr(reg_mod, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(scanner_mod, "PROJECT_ROOT", tmp_path)
    (tmp_path / "data").mkdir(parents=True)

    src = get_source("uscis_inventory")
    result = scan_source(src, html_override=SAMPLE_USCIS_HTML, delay=0)
    assert len(result.candidates) == 1
    assert "eb_inventory" in result.candidates[0].filename


def test_scan_visa_bulletin_records_pages(tmp_path, monkeypatch):
    import src.ingestion.scanner as scanner_mod
    import src.ingestion.registry as reg_mod

    monkeypatch.setattr(reg_mod, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(scanner_mod, "PROJECT_ROOT", tmp_path)
    vb_dir = tmp_path / "data" / "visa_bulletin"
    vb_dir.mkdir(parents=True)
    seen = vb_dir / ".seen_bulletins.txt"
    seen.write_text(
        "https://travel.state.gov/content/travel/en/legal/visa-law0/visa-bulletin/2026/visa-bulletin-for-june-2026.html\n"
    )

    src = get_source("visa_bulletin")
    result = scan_source(src, html_override=SAMPLE_VB_HTML, delay=0)
    assert len(result.candidates) == 2
    june = next(c for c in result.candidates if "june" in c.filename)
    july = next(c for c in result.candidates if "july" in c.filename)
    assert june.status == "exists"
    assert july.status == "new"
    assert july.content_type == "bulletin_page"


def test_scan_source_http_error_recorded():
    src = get_source("dos_iv_fsc")
    mock_sess = MagicMock()
    mock_resp = MagicMock()
    mock_resp.raise_for_status.side_effect = Exception("404 not found")
    mock_sess.get.return_value = mock_resp

    with patch("src.ingestion.scanner.requests") as req_mod:
        req_mod.Session.return_value = mock_sess
        # pass session directly so _fetch_html uses it
        result = scan_source(src, session=mock_sess, delay=0)
    # Exception is caught as generic Exception in _fetch_html
    # Actually raise_for_status side effect Exception gets caught
    assert result.page_fetched is False or result.errors


def test_scan_source_network_failure():
    src = get_source("dos_iv_fsc")

    class BoomSession:
        def get(self, *a, **k):
            raise ConnectionError("network down")

    result = scan_source(src, session=BoomSession(), delay=0)
    assert result.page_fetched is False
    assert result.errors
    assert "ConnectionError" in result.errors[0]


# ── Fetcher ─────────────────────────────────────────────────────────────────


def test_fetch_candidate_dry_run(tmp_path):
    cand = RemoteCandidate(
        source_id="dos_iv_fsc",
        agency="DOS",
        url="https://example.com/file.xlsx",
        filename="file.xlsx",
        target_path=tmp_path / "file.xlsx",
        status="new",
        content_type="file",
    )
    fr = fetch_candidate(cand, dry_run=True, delay=0)
    assert fr.success
    assert fr.dry_run
    assert not (tmp_path / "file.xlsx").exists()


def test_fetch_candidate_skips_existing(tmp_path):
    dest = tmp_path / "file.xlsx"
    dest.write_bytes(b"x")
    cand = RemoteCandidate(
        source_id="dos_iv_fsc",
        agency="DOS",
        url="https://example.com/file.xlsx",
        filename="file.xlsx",
        target_path=dest,
        status="exists",
        content_type="file",
    )
    fr = fetch_candidate(cand, delay=0)
    assert fr.skipped
    assert fr.success


def test_fetch_candidate_downloads(tmp_path):
    dest = tmp_path / "file.xlsx"
    cand = RemoteCandidate(
        source_id="dos_iv_fsc",
        agency="DOS",
        url="https://example.com/file.xlsx",
        filename="file.xlsx",
        target_path=dest,
        status="new",
        content_type="file",
    )

    class FakeResp:
        def raise_for_status(self):
            pass

        def iter_content(self, chunk_size=65536):
            yield b"PK\x03\x04fake-xlsx-bytes"

    class FakeSess:
        def get(self, *a, **k):
            return FakeResp()

    fr = fetch_candidate(cand, session=FakeSess(), delay=0)
    assert fr.success
    assert dest.exists()
    assert fr.bytes_written > 0


def test_fetch_bulletin_records_seen_file(tmp_path):
    seen = tmp_path / ".seen_bulletins.txt"
    cand = RemoteCandidate(
        source_id="visa_bulletin",
        agency="DOS",
        url="https://travel.state.gov/.../visa-bulletin-for-july-2026.html",
        filename="visa-bulletin-for-july-2026.html",
        target_path=seen,
        status="new",
        content_type="bulletin_page",
    )
    fr = fetch_candidate(cand, delay=0)
    assert fr.success
    assert seen.exists()
    assert "july-2026" in seen.read_text()


def test_fetch_candidates_new_only():
    c_new = RemoteCandidate(
        source_id="x",
        agency="USCIS",
        url="http://x/a.xlsx",
        filename="a.xlsx",
        target_path=Path("/tmp/a.xlsx"),
        status="new",
        content_type="file",
    )
    c_old = RemoteCandidate(
        source_id="x",
        agency="USCIS",
        url="http://x/b.xlsx",
        filename="b.xlsx",
        target_path=Path("/tmp/b.xlsx"),
        status="exists",
        content_type="file",
    )
    results = fetch_candidates([c_new, c_old], dry_run=True, delay=0, new_only=True)
    assert len(results) == 1
    assert results[0].candidate.filename == "a.xlsx"


# ── PR helper ───────────────────────────────────────────────────────────────


def test_propose_branch_name():
    from datetime import date

    name = propose_branch_name(["dos_iv_fsc"], when=date(2026, 6, 23))
    assert name == "chore/data-dos_iv_fsc-2026-06-23"
    multi = propose_branch_name(["a", "b"], when=date(2026, 1, 1))
    assert multi == "chore/data-multi-2026-01-01"


def test_build_pr_body_includes_engine_notes():
    from src.ingestion.scanner import ScanResult

    sr = ScanResult(source_id="dos_iv_fsc", scan_url="http://x")
    sr.candidates.append(
        RemoteCandidate(
            source_id="dos_iv_fsc",
            agency="DOS",
            url="http://x/f.xlsx",
            filename="f.xlsx",
            status="new",
        )
    )
    body = build_pr_body([sr], ["data/DOS/f.xlsx"], source_ids=["dos_iv_fsc"])
    assert "dos_iv_fsc" in body
    assert "DOSParser" in body or "data/DOS" in body
    assert "f.xlsx" in body


def test_paths_from_fetch_results(tmp_path, monkeypatch):
    import src.ingestion.pr_helper as pr_mod

    monkeypatch.setattr(pr_mod, "PROJECT_ROOT", tmp_path)
    f = tmp_path / "data" / "DOS" / "x.xlsx"
    f.parent.mkdir(parents=True)
    f.write_bytes(b"x")
    cand = RemoteCandidate(
        source_id="dos_iv_fsc",
        agency="DOS",
        url="http://x",
        filename="x.xlsx",
        target_path=f,
        status="fetched",
        content_type="file",
    )
    fr = FetchResult(candidate=cand, success=True, path=f, bytes_written=1)
    paths = paths_from_fetch_results([fr])
    assert paths == ["data/DOS/x.xlsx"]


def test_create_data_pr_dry_run():
    from src.ingestion.pr_helper import create_data_pr

    r = create_data_pr(
        files=["data/DOS/x.xlsx"],
        source_ids=["dos_iv_fsc"],
        dry_run=True,
    )
    assert r.success
    assert r.dry_run
    assert "chore/data-" in r.branch


# ── CLI smoke ───────────────────────────────────────────────────────────────


def test_scan_and_pr_list_sources():
    from src.scripts.scan_and_pr import main

    assert main(["--list-sources"]) == 0


def test_scan_and_pr_scan_with_html_mock(tmp_path, monkeypatch, capsys):
    """End-to-end CLI path with scan_source monkeypatched to avoid network."""
    from src.ingestion.scanner import ScanResult
    from src.scripts import scan_and_pr as cli

    fake = ScanResult(source_id="dos_iv_fsc", scan_url="http://x", page_fetched=True)

    def fake_scan_sources(*a, **k):
        return [fake]

    monkeypatch.setattr(cli, "scan_sources", fake_scan_sources)
    rc = cli.main(["--scan", "--source", "dos_iv", "--dry-run"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "dos_iv_fsc" in out or "Scanning" in out


# ── Optional live integration (skipped by default) ──────────────────────────


@pytest.mark.integration
def test_live_dos_page_has_fsc_links():
    """Live network: DOS monthly IV page should expose FSC xlsx links."""
    import requests
    from src.ingestion.registry import USER_AGENT, get_source
    from src.ingestion.scanner import extract_links

    src = get_source("dos_iv_fsc")
    r = requests.get(src.scan_url, headers={"User-Agent": USER_AGENT}, timeout=45)
    r.raise_for_status()
    links = extract_links(r.text, src.scan_url)
    fsc = [
        u
        for u, t in links
        if u.lower().endswith(".xlsx")
        and ("FSC" in u or "FSC" in t or "Place%20of%20Birth" in u)
    ]
    assert len(fsc) >= 10, f"expected many FSC links, got {len(fsc)}"


@pytest.mark.integration
def test_live_uscis_page_has_eb_or_i485_xlsx():
    import requests
    from src.ingestion.registry import USER_AGENT, get_source
    from src.ingestion.scanner import extract_links

    src = get_source("uscis_i140")
    r = requests.get(src.scan_url, headers={"User-Agent": USER_AGENT}, timeout=45)
    r.raise_for_status()
    links = extract_links(r.text, src.scan_url)
    xlsx = [u for u, _ in links if u.lower().endswith((".xlsx", ".xls"))]
    assert len(xlsx) >= 1
