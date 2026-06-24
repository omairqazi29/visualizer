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


def test_fetch_candidate_dry_run(tmp_path, monkeypatch):
    from src.ingestion import fetcher as fetcher_mod

    monkeypatch.setattr(fetcher_mod, "is_under_data_dir", lambda p: True)
    cand = RemoteCandidate(
        source_id="dos_iv_fsc",
        agency="DOS",
        url="https://travel.state.gov/file.xlsx",
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
        url="https://travel.state.gov/file.xlsx",
        filename="file.xlsx",
        target_path=dest,
        status="exists",
        content_type="file",
    )
    fr = fetch_candidate(cand, delay=0)
    assert fr.skipped
    assert fr.success


def test_fetch_candidate_downloads(tmp_path, monkeypatch):
    from src.ingestion import fetcher as fetcher_mod

    monkeypatch.setattr(fetcher_mod, "is_under_data_dir", lambda p: True)
    dest = tmp_path / "file.xlsx"
    cand = RemoteCandidate(
        source_id="dos_iv_fsc",
        agency="DOS",
        url="https://travel.state.gov/file.xlsx",
        filename="file.xlsx",
        target_path=dest,
        status="new",
        content_type="file",
    )

    class FakeResp:
        url = "https://travel.state.gov/file.xlsx"
        headers = {"Content-Type": "application/octet-stream"}

        def raise_for_status(self):
            pass

        def iter_content(self, chunk_size=65536):
            yield b"PK\x03\x04fake-xlsx-bytes"

    class FakeSess:
        def get(self, *a, **k):
            return FakeResp()

    fr = fetch_candidate(cand, session=FakeSess(), delay=0)
    assert fr.success, fr.error
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
    from src.ingestion.registry import PROJECT_ROOT as REAL_ROOT

    # Use real project data/ path so is_under_data_dir passes
    f = REAL_ROOT / "data" / "DOS"
    if not f.exists():
        pytest.skip("no data/DOS in repo")
    sample = next(f.glob("*.xlsx"), None)
    if sample is None:
        pytest.skip("no DOS xlsx")
    cand = RemoteCandidate(
        source_id="dos_iv_fsc",
        agency="DOS",
        url="http://x",
        filename=sample.name,
        target_path=sample,
        status="fetched",
        content_type="file",
    )
    fr = FetchResult(candidate=cand, success=True, path=sample, bytes_written=1)
    paths = paths_from_fetch_results([fr])
    assert len(paths) == 1
    assert paths[0].startswith("data/")


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

# ── Security ─────────────────────────────────────────────────────────────────


def test_safe_basename_rejects_traversal():
    from src.ingestion.security import safe_basename
    import pytest

    assert safe_basename("ok_file.xlsx") == "ok_file.xlsx"
    with pytest.raises(ValueError):
        safe_basename("../../../evil.xlsx")
    with pytest.raises(ValueError):
        safe_basename("foo/bar.xlsx")


def test_safe_target_path_stays_under_dir(tmp_path):
    from src.ingestion.security import safe_target_path
    import pytest

    dest = safe_target_path(tmp_path, "good.xlsx")
    assert dest.parent == tmp_path.resolve()
    with pytest.raises(ValueError):
        safe_target_path(tmp_path, "../escape.xlsx")


def test_is_allowed_url_host_and_scheme():
    from src.ingestion.security import is_allowed_url

    ok, _ = is_allowed_url("https://travel.state.gov/x.xlsx", ("travel.state.gov",))
    assert ok
    ok, reason = is_allowed_url("https://evil.com/x.xlsx", ("travel.state.gov",))
    assert not ok
    ok, reason = is_allowed_url("ftp://travel.state.gov/x", ("travel.state.gov",))
    assert not ok
    ok, _ = is_allowed_url("https://sub.uscis.gov/a", ("uscis.gov",))
    assert ok


def test_scan_rejects_offsite_candidate_via_allowlist(tmp_path, monkeypatch):
    import src.ingestion.scanner as scanner_mod
    import src.ingestion.registry as reg_mod

    monkeypatch.setattr(reg_mod, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(scanner_mod, "PROJECT_ROOT", tmp_path)
    (tmp_path / "data" / "DOS").mkdir(parents=True)

    html = (
        '<html><body>'
        '<a href="https://evil.example/IV%20Issuances%20by%20FSC%20or%20Place%20of%20Birth.xlsx">bad</a>'
        '<a href="https://travel.state.gov/content/dam/x/JANUARY%202026%20-%20IV%20Issuances%20by%20FSC%20or%20Place%20of%20Birth%20and%20Visa%20Class.xlsx">good</a>'
        '</body></html>'
    )
    src = get_source("dos_iv_fsc")
    result = scan_source(src, html_override=html, delay=0)
    urls = [c.url for c in result.candidates]
    assert all("evil.example" not in u for u in urls)
    assert any("travel.state.gov" in u for u in urls)


def test_target_path_for_rejects_traversal():
    from src.ingestion.registry import target_path_for
    import pytest

    src = get_source("dos_iv_fsc")
    with pytest.raises(ValueError):
        target_path_for(src, "../../outside.xlsx")


def test_uscis_i140_and_i140_rec_not_collapsed(tmp_path, monkeypatch):
    import src.ingestion.scanner as scanner_mod
    import src.ingestion.registry as reg_mod

    monkeypatch.setattr(reg_mod, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(scanner_mod, "PROJECT_ROOT", tmp_path)
    (tmp_path / "data").mkdir(parents=True)
    (tmp_path / "data" / "i140_rec_by_class_country_fy2026_q1_v1.xlsx").write_bytes(b"PK\x03\x04x")

    html = (
        '<html><body>'
        '<a href="/sites/default/files/document/reports/eb_i140_i360_i526_performancedata_fy2026_q1_v1.xlsx">EB perf</a>'
        '<a href="/sites/default/files/document/reports/i140_rec_by_class_country_fy2026_q1_v1.xlsx">I-140 rec</a>'
        '</body></html>'
    )
    src = get_source("uscis_i140")
    result = scan_source(src, html_override=html, delay=0)
    by_name = {c.filename: c.status for c in result.candidates}
    assert by_name["i140_rec_by_class_country_fy2026_q1_v1.xlsx"] == "exists"
    assert by_name["eb_i140_i360_i526_performancedata_fy2026_q1_v1.xlsx"] == "new"


def test_uscis_performance_data_variant_matches_local(tmp_path, monkeypatch):
    """performancedata vs performance_data + _v1 suffix only (not different form stems)."""
    import src.ingestion.scanner as scanner_mod
    import src.ingestion.registry as reg_mod

    monkeypatch.setattr(reg_mod, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(scanner_mod, "PROJECT_ROOT", tmp_path)
    d = tmp_path / "data" / "USCIS_I485"
    d.mkdir(parents=True)
    # Local uses performancedata; remote uses performance_data + _v1
    (d / "i485_performancedata_fy2026_q1.xlsx").write_bytes(b"PK\x03\x04x")

    html = (
        '<html><body>'
        '<a href="/sites/default/files/document/reports/i485_performance_data_fy2026_q1_v1.xlsx">perf</a>'
        '</body></html>'
    )
    src = get_source("uscis_i485_perf")
    result = scan_source(src, html_override=html, delay=0)
    assert len(result.candidates) == 1
    assert result.candidates[0].status == "exists"


def test_dos_v1_suffix_dedup(tmp_path, monkeypatch):
    import src.ingestion.scanner as scanner_mod
    import src.ingestion.registry as reg_mod

    monkeypatch.setattr(reg_mod, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(scanner_mod, "PROJECT_ROOT", tmp_path)
    dos = tmp_path / "data" / "DOS"
    dos.mkdir(parents=True)
    (dos / "DECEMBER 2022 - IV Issuances by FSC or Place of Birth and Visa Class.xlsx").write_bytes(b"x")

    # Basename must pass safe_basename (no path segments in stored name)
    html = (
        '<html><body>'
        '<a href="https://travel.state.gov/dam/visas/DECEMBER%202022%20-%20IV%20Issuances%20by%20FSC%20or%20Place%20of%20Birth%20and%20Visa%20Class_v1.xlsx">Excel</a>'
        '</body></html>'
    )
    src = get_source("dos_iv_fsc")
    result = scan_source(src, html_override=html, delay=0)
    assert len(result.candidates) >= 1
    assert result.candidates[0].status == "exists"


def test_vb_year_filter_excludes_old(tmp_path, monkeypatch):
    import src.ingestion.scanner as scanner_mod
    import src.ingestion.registry as reg_mod

    monkeypatch.setattr(reg_mod, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(scanner_mod, "PROJECT_ROOT", tmp_path)
    (tmp_path / "data" / "visa_bulletin").mkdir(parents=True)

    html = (
        '<html><body>'
        '<a href="/content/travel/en/legal/visa-law0/visa-bulletin/2010/visa-bulletin-for-april-2010.html">old</a>'
        '<a href="/content/travel/en/legal/visa-law0/visa-bulletin/2026/visa-bulletin-for-july-2026.html">new</a>'
        '</body></html>'
    )
    src = get_source("visa_bulletin")
    result = scan_source(src, html_override=html, delay=0)
    names = [c.filename for c in result.candidates]
    assert "visa-bulletin-for-july-2026.html" in names
    assert "visa-bulletin-for-april-2010.html" not in names


def test_kind_for_path_and_missing():
    from src.ingestion.validator import _kind_for_path, validate_path

    assert _kind_for_path(Path("/tmp/DOS/foo.xlsx")) == "dos"
    assert _kind_for_path(Path("data/eb_inventory_april_2026.xlsx")) == "inventory"
    item = validate_path(Path("/nonexistent/file.xlsx"))
    assert item.ok is False
    assert item.kind == "missing"


def test_validate_empty_file(tmp_path):
    from src.ingestion.validator import validate_path

    p = tmp_path / "eb_inventory_test.xlsx"
    p.write_bytes(b"")
    item = validate_path(p)
    assert item.ok is False


def test_validate_unknown_strict(tmp_path):
    from src.ingestion.validator import validate_path

    p = tmp_path / "random_notes.txt"
    p.write_text("hello")
    assert validate_path(p, strict_unknown=False).ok is True
    assert validate_path(p, strict_unknown=True).ok is False


def test_validate_report_ok_aggregate(tmp_path):
    from src.ingestion.validator import validate_downloaded_files

    p = tmp_path / "missing.xlsx"
    report = validate_downloaded_files(paths=[p])
    assert report.ok is False


def test_validate_real_dos_single_file_if_present():
    from src.ingestion.validator import validate_path
    from src.data_discovery import get_dos_dir

    dos_dir = Path(get_dos_dir())
    files = list(dos_dir.glob("*.xlsx")) if dos_dir.exists() else []
    if not files:
        pytest.skip("no DOS files in repo")
    item = validate_path(files[0])
    assert item.ok is True
    assert item.kind == "dos"


def test_fetch_refuses_outside_data(tmp_path):
    from src.ingestion.fetcher import fetch_candidate

    cand = RemoteCandidate(
        source_id="dos_iv_fsc",
        agency="DOS",
        url="https://travel.state.gov/x.xlsx",
        filename="x.xlsx",
        target_path=tmp_path / "outside.xlsx",
        status="new",
        content_type="file",
    )
    fr = fetch_candidate(cand, delay=0)
    assert fr.success is False
    assert "data" in fr.error.lower() or "outside" in fr.error.lower()


def test_fetch_cleans_part_on_failure(tmp_path, monkeypatch):
    from src.ingestion import fetcher as fetcher_mod

    monkeypatch.setattr(fetcher_mod, "is_under_data_dir", lambda p: True)
    dest = tmp_path / "file.xlsx"
    cand = RemoteCandidate(
        source_id="dos_iv_fsc",
        agency="DOS",
        url="https://travel.state.gov/x.xlsx",
        filename="file.xlsx",
        target_path=dest,
        status="new",
        content_type="file",
    )

    class BoomSess:
        def get(self, *a, **k):
            raise ConnectionError("boom")

    fr = fetcher_mod.fetch_candidate(cand, session=BoomSess(), delay=0)
    assert fr.success is False
    assert not list(tmp_path.glob("*.part"))


def test_any_fetch_failed():
    from src.ingestion.fetcher import any_fetch_failed, FetchResult

    c = RemoteCandidate(
        source_id="x", agency="DOS", url="u", filename="f", status="new", content_type="file"
    )
    ok = FetchResult(candidate=c, success=True, skipped=True)
    bad = FetchResult(candidate=c, success=False, error="nope")
    assert any_fetch_failed([ok]) is False
    assert any_fetch_failed([ok, bad]) is True


def test_propose_branch_name_includes_run_id(monkeypatch):
    from datetime import date
    from src.ingestion.pr_helper import propose_branch_name

    monkeypatch.setenv("GITHUB_RUN_ID", "12345678")
    name = propose_branch_name(["dos_iv_fsc"], when=date(2026, 6, 23))
    assert "12345678" in name
    assert name.startswith("chore/data-dos_iv_fsc-2026-06-23")


def test_sanitize_pr_filename():
    from src.ingestion.security import sanitize_pr_filename

    assert "`" not in sanitize_pr_filename("bad`name.xlsx")
    assert len(sanitize_pr_filename("a" * 200)) <= 120


def test_create_data_pr_git_unavailable(monkeypatch):
    from src.ingestion.pr_helper import create_data_pr

    monkeypatch.setattr("src.ingestion.pr_helper._git_available", lambda: False)
    r = create_data_pr(files=["data/DOS/x.xlsx"], source_ids=["dos_iv_fsc"], dry_run=False)
    assert r.success is False
    assert "git not available" in r.message


def test_create_data_pr_nothing_staged(monkeypatch):
    from src.ingestion.pr_helper import create_data_pr
    from subprocess import CompletedProcess

    def fake_run(cmd, **kwargs):
        if cmd[:2] == ["git", "rev-parse"]:
            return CompletedProcess(cmd, 0, stdout="master\n", stderr="")
        if cmd[:2] == ["git", "checkout"]:
            return CompletedProcess(cmd, 0, stdout="", stderr="")
        if cmd[:2] == ["git", "add"]:
            return CompletedProcess(cmd, 0, stdout="", stderr="")
        if cmd[:3] == ["git", "diff", "--cached"]:
            return CompletedProcess(cmd, 0, stdout="", stderr="")
        return CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr("src.ingestion.pr_helper._git_available", lambda: True)
    monkeypatch.setattr("src.ingestion.pr_helper._run", fake_run)
    r = create_data_pr(
        files=["data/DOS/x.xlsx"],
        source_ids=["dos_iv_fsc"],
        dry_run=False,
        restore_branch=False,
    )
    assert r.success is False
    assert "nothing staged" in r.message


def test_create_data_pr_success_with_mocks(monkeypatch):
    from src.ingestion.pr_helper import create_data_pr
    from subprocess import CompletedProcess

    def fake_run(cmd, **kwargs):
        if cmd[:2] == ["git", "rev-parse"] and "abbrev-ref" in cmd:
            return CompletedProcess(cmd, 0, stdout="master\n", stderr="")
        if cmd[:2] == ["git", "rev-parse"]:
            return CompletedProcess(cmd, 0, stdout="abc123\n", stderr="")
        if cmd[:2] == ["git", "checkout"]:
            return CompletedProcess(cmd, 0, stdout="", stderr="")
        if cmd[:2] == ["git", "add"]:
            return CompletedProcess(cmd, 0, stdout="", stderr="")
        if cmd[:3] == ["git", "diff", "--cached"]:
            return CompletedProcess(cmd, 0, stdout="data/DOS/x.xlsx\n", stderr="")
        if cmd[:2] == ["git", "commit"]:
            return CompletedProcess(cmd, 0, stdout="", stderr="")
        if cmd[:2] == ["git", "push"]:
            return CompletedProcess(cmd, 0, stdout="", stderr="")
        if cmd[:2] == ["gh", "pr"]:
            return CompletedProcess(cmd, 0, stdout="https://github.com/x/y/pull/1\n", stderr="")
        return CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr("src.ingestion.pr_helper._git_available", lambda: True)
    monkeypatch.setattr("src.ingestion.pr_helper._gh_available", lambda: True)
    monkeypatch.setattr("src.ingestion.pr_helper._run", fake_run)
    monkeypatch.setattr("src.ingestion.pr_helper.filter_paths_for_pr", lambda files: list(files))

    r = create_data_pr(
        files=["data/DOS/x.xlsx"],
        source_ids=["dos_iv_fsc"],
        dry_run=False,
        base_branch="master",
        restore_branch=True,
    )
    assert r.success is True
    assert "pull/1" in r.pr_url


def test_create_data_pr_gh_missing_still_success(monkeypatch):
    from src.ingestion.pr_helper import create_data_pr
    from subprocess import CompletedProcess

    def fake_run(cmd, **kwargs):
        if cmd[:2] == ["git", "rev-parse"] and "abbrev-ref" in cmd:
            return CompletedProcess(cmd, 0, stdout="master\n", stderr="")
        if cmd[:2] == ["git", "rev-parse"]:
            return CompletedProcess(cmd, 0, stdout="abc\n", stderr="")
        if cmd[:2] == ["git", "checkout"]:
            return CompletedProcess(cmd, 0, stdout="", stderr="")
        if cmd[:2] == ["git", "add"]:
            return CompletedProcess(cmd, 0, stdout="", stderr="")
        if cmd[:3] == ["git", "diff", "--cached"]:
            return CompletedProcess(cmd, 0, stdout="data/DOS/x.xlsx\n", stderr="")
        if cmd[:2] == ["git", "commit"]:
            return CompletedProcess(cmd, 0, stdout="", stderr="")
        if cmd[:2] == ["git", "push"]:
            return CompletedProcess(cmd, 0, stdout="", stderr="")
        return CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr("src.ingestion.pr_helper._git_available", lambda: True)
    monkeypatch.setattr("src.ingestion.pr_helper._gh_available", lambda: False)
    monkeypatch.setattr("src.ingestion.pr_helper._run", fake_run)
    monkeypatch.setattr("src.ingestion.pr_helper.filter_paths_for_pr", lambda files: list(files))

    r = create_data_pr(
        files=["data/DOS/x.xlsx"],
        source_ids=["dos_iv_fsc"],
        dry_run=False,
        restore_branch=False,
    )
    assert r.success is True
    assert "gh CLI not available" in r.message


def test_cli_invalid_source_exit_2():
    from src.scripts.scan_and_pr import main

    assert main(["--source", "not_a_real_thing"]) == 2


def test_cli_scan_failure_exit_1(monkeypatch):
    from src.scripts import scan_and_pr as cli
    from src.ingestion.scanner import ScanResult as SR

    def bad_scan(*a, **k):
        r = SR(source_id="dos_iv_fsc", scan_url="http://x", page_fetched=False)
        r.errors.append("ConnectionError: down")
        return [r]

    monkeypatch.setattr(cli, "scan_sources", bad_scan)
    rc = cli.main(["--scan", "--source", "dos_iv"])
    assert rc == 1


def test_cli_fetch_failure_blocks_pr(monkeypatch):
    from src.scripts import scan_and_pr as cli
    from src.ingestion.fetcher import FetchResult
    from src.ingestion.scanner import ScanResult as SR

    sr = SR(source_id="dos_iv_fsc", scan_url="http://x", page_fetched=True)
    cand = RemoteCandidate(
        source_id="dos_iv_fsc",
        agency="DOS",
        url="http://x/f.xlsx",
        filename="f.xlsx",
        status="new",
        content_type="file",
        target_path=Path("/tmp/f.xlsx"),
    )
    sr.candidates.append(cand)

    monkeypatch.setattr(cli, "scan_sources", lambda *a, **k: [sr])
    monkeypatch.setattr(
        cli,
        "fetch_from_scan_results",
        lambda *a, **k: [FetchResult(candidate=cand, success=False, error="boom")],
    )
    rc = cli.main(["--scan", "--fetch", "--pr", "--source", "dos_iv"])
    assert rc == 1


def test_cli_json_flag_emits_json(monkeypatch, capsys):
    from src.scripts import scan_and_pr as cli
    from src.ingestion.scanner import ScanResult as SR

    monkeypatch.setattr(
        cli,
        "scan_sources",
        lambda *a, **k: [SR(source_id="dos_iv_fsc", scan_url="http://x", page_fetched=True)],
    )
    rc = cli.main(["--scan", "--source", "dos_iv", "--dry-run", "--json"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "source_ids" in out


def test_all_group_excludes_visa_bulletin():
    ids = resolve_source_ids("all")
    assert "visa_bulletin" not in ids
    assert "dos_iv_fsc" in ids
    assert "visa_bulletin" in resolve_source_ids("all_including_vb")


def test_disabled_stubs_present():
    from src.ingestion.registry import SOURCE_REGISTRY as REG

    assert "nvc_waiting_list" in REG
    assert REG["nvc_waiting_list"].enabled is False
    assert "ceac_scheduling" in REG
