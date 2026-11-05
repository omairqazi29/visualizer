"""Upstream 403 classification and scan_and_pr exit behavior.

DOS Cloudflare 403s and plain HTTP 403s from the USCIS and DHS hosts those
sources already scan share one access_blocked path. DOL and any other host,
plus non-403 failures, stay hard failures.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.ingestion.http_client import (
    classify_response,
    html_request_headers,
    is_known_upstream_host,
    is_upstream_access_block,
)
from src.ingestion.scanner import ScanResult, summarize_scan

VB_URL = "https://travel.state.gov/content/travel/en/legal/visa-law0/visa-bulletin.html"
DOS_URL = (
    "https://travel.state.gov/content/travel/en/legal/visa-law0/"
    "visa-statistics/immigrant-visa-statistics/monthly-immigrant-visa-issuances.html"
)
USCIS_URL = "https://www.uscis.gov/tools/reports-and-studies/immigration-and-citizenship-data"
DHS_URL = "https://ohss.dhs.gov/topics/immigration/yearbook"
DOL_URL = "https://www.dol.gov/agencies/eta/foreign-labor/performance"
EGOV_USCIS_URL = "https://egov.uscis.gov/processing-times/"
WWW_DHS_URL = "https://www.dhs.gov/topics/immigration/yearbook"
LEGACY_VB_403 = (
    "HTTPError: 403 Client Error: Forbidden for url: " + VB_URL
)
LEGACY_DOS_403 = (
    "HTTPError: 403 Client Error: Forbidden for url: " + DOS_URL
)


def _http_error(status: int, url: str, reason: str = "Forbidden") -> str:
    return f"HTTPError: {status} Client Error: {reason} for url: {url}"


# Exact strings from data-scan run 42107407094 (master @ 13298a4).
RUN_42107407094_USCIS_403 = _http_error(403, USCIS_URL)
RUN_42107407094_DHS_403 = _http_error(403, DHS_URL)


class _Resp:
    def __init__(self, status, url, headers=None, body=b"", reason="Forbidden"):
        self.status_code = status
        self.url = url
        self.headers = headers or {}
        self.content = body
        self.reason = reason

    def raise_for_status(self):
        raise AssertionError("raise_for_status should not run for classified HTTP errors")


def test_browser_headers_are_static_and_identified():
    headers = html_request_headers()
    assert "Mozilla/5.0" in headers["User-Agent"]
    assert "Chrome/" in headers["User-Agent"]
    assert "Accept-Language" in headers
    assert "Accept" in headers
    # No challenge-solver / impersonation library hooks.
    assert "cloudscraper" not in headers["User-Agent"].lower()


@pytest.mark.parametrize(
    "status,url,headers,body,expect_block,expect_cf",
    [
        (
            403,
            VB_URL,
            {"Server": "cloudflare", "CF-RAY": "abc-SEA"},
            b"<title>Attention Required! | Cloudflare</title>Sorry, you have been blocked",
            True,
            True,
        ),
        (403, DOS_URL, {}, b"", True, False),
        (403, "https://ceac.state.gov/CEAC/", {}, b"", True, False),
        (
            403,
            USCIS_URL,
            {"Server": "cloudflare", "CF-RAY": "abc"},
            b"Attention Required! | Cloudflare",
            True,
            True,
        ),
        (403, USCIS_URL, {}, b"", True, False),
        (403, DHS_URL, {}, b"", True, False),
        (403, EGOV_USCIS_URL, {}, b"", True, False),
        (403, WWW_DHS_URL, {}, b"", True, False),
        (403, DOL_URL, {}, b"", False, False),
        (403, "https://uscis.gov.evil.example/data", {}, b"", False, False),
        (404, USCIS_URL, {}, b"missing", False, False),
        (500, DHS_URL, {}, b"error", False, False),
        (503, USCIS_URL, {}, b"gateway timeout", False, False),
        (
            503,
            USCIS_URL,
            {"Server": "cloudflare", "cf-ray": "usc"},
            b"Just a moment",
            True,
            True,
        ),
        (404, VB_URL, {"Server": "cloudflare"}, b"not found", False, False),
        (500, DOS_URL, {"Server": "cloudflare"}, b"cloudflare", False, False),
        (
            503,
            DOS_URL,
            {"Server": "cloudflare", "cf-ray": "zzz"},
            b"Just a moment",
            True,
            True,
        ),
        (503, DOS_URL, {}, b"gateway timeout", False, False),
    ],
)
def test_classify_response_dos_403_versus_real_errors(
    status, url, headers, body, expect_block, expect_cf
):
    block = classify_response(url=url, status=status, headers=headers, body=body.decode())
    if expect_block:
        assert block is not None
        assert block.cloudflare is expect_cf
        assert block.message.startswith("UPSTREAM ACCESS BLOCKED:")
        assert "not a broken scanner URL" in block.message
    else:
        assert block is None


def test_legacy_gha_403_strings_match_failing_runs():
    """The exact HTTPError text from the red scheduled runs is an access block."""
    assert is_upstream_access_block(LEGACY_VB_403, VB_URL)
    assert is_upstream_access_block(LEGACY_DOS_403, DOS_URL)
    assert is_upstream_access_block(RUN_42107407094_USCIS_403, USCIS_URL)
    assert is_upstream_access_block(RUN_42107407094_DHS_403, DHS_URL)
    assert not is_upstream_access_block(
        "HTTPError: 404 Client Error: Not Found for url: " + VB_URL, VB_URL
    )
    assert not is_upstream_access_block(_http_error(404, USCIS_URL, "Not Found"), USCIS_URL)
    assert not is_upstream_access_block(_http_error(500, DHS_URL, "Server Error"), DHS_URL)
    assert not is_upstream_access_block(_http_error(403, DOL_URL), DOL_URL)
    assert not is_upstream_access_block("ConnectionError: down", DOS_URL)
    assert not is_upstream_access_block("ConnectionError: down", USCIS_URL)
    assert not is_upstream_access_block("Timeout: timed out", VB_URL)
    assert not is_upstream_access_block("Timeout: timed out", DHS_URL)


def test_scan_source_cloudflare_403_sets_access_blocked():
    from src.ingestion.registry import get_source
    from src.ingestion.scanner import scan_source

    src = get_source("visa_bulletin")

    class Session:
        def get(self, *args, **kwargs):
            return _Resp(
                403,
                VB_URL,
                headers={"Server": "cloudflare", "CF-RAY": "a3f7c3f4fcb634a1-SJC"},
                body=(
                    b"<html><title>Attention Required! | Cloudflare</title>"
                    b"Sorry, you have been blocked</html>"
                ),
            )

    result = scan_source(src, session=Session(), delay=0)
    assert result.page_fetched is False
    assert result.access_blocked is True
    assert result.errors
    assert result.errors[0].startswith("UPSTREAM ACCESS BLOCKED:")
    assert "Cloudflare" in result.errors[0]
    summary = summarize_scan([result])
    assert "[BLOCKED] visa_bulletin" in summary
    assert "UPSTREAM ACCESS BLOCKED:" in summary
    assert "[FAIL] visa_bulletin" not in summary


@pytest.mark.parametrize(
    "source_id,url",
    [
        ("uscis_inventory", USCIS_URL),
        ("uscis_i485_perf", USCIS_URL),
        ("uscis_i140", USCIS_URL),
        ("uscis_i485_monthly_csv", USCIS_URL),
        ("dhs_yearbook", DHS_URL),
    ],
)
def test_scan_source_uscis_dhs_403_sets_access_blocked(source_id, url):
    """Plain HTTP 403 (no Cloudflare markers) is the run 42107407094 shape."""
    from src.ingestion.registry import get_source
    from src.ingestion.scanner import scan_source

    src = get_source(source_id)

    class Session:
        def get(self, *args, **kwargs):
            return _Resp(403, url, body=b"Forbidden")

    result = scan_source(src, session=Session(), delay=0)
    assert result.page_fetched is False
    assert result.access_blocked is True
    assert result.errors
    assert result.errors[0].startswith("UPSTREAM ACCESS BLOCKED:")
    assert "not a broken scanner URL" in result.errors[0]
    summary = summarize_scan([result])
    assert f"[BLOCKED] {source_id}" in summary
    assert f"[FAIL] {source_id}" not in summary


def test_scan_source_dol_403_is_not_an_access_block():
    from src.ingestion.registry import get_source
    from src.ingestion.scanner import scan_source

    src = get_source("dol_perm")

    class Session:
        def get(self, *args, **kwargs):
            return _Resp(403, DOL_URL, body=b"Forbidden")

    result = scan_source(src, session=Session(), delay=0)
    assert result.page_fetched is False
    assert result.access_blocked is False
    assert "403" in result.errors[0]
    assert not result.errors[0].startswith("UPSTREAM ACCESS BLOCKED:")
    summary = summarize_scan([result])
    assert "[FAIL] dol_perm" in summary
    assert "[BLOCKED] dol_perm" not in summary


@pytest.mark.parametrize(
    "source_id,url,status,reason",
    [
        ("uscis_inventory", USCIS_URL, 404, "Not Found"),
        ("uscis_i140", USCIS_URL, 500, "Server Error"),
        ("dhs_yearbook", DHS_URL, 404, "Not Found"),
        ("dhs_yearbook", DHS_URL, 503, "Service Unavailable"),
    ],
)
def test_scan_source_uscis_dhs_non_403_is_not_an_access_block(source_id, url, status, reason):
    from src.ingestion.registry import get_source
    from src.ingestion.scanner import scan_source

    src = get_source(source_id)

    class Session:
        def get(self, *args, **kwargs):
            return _Resp(status, url, reason=reason, body=b"nope")

    result = scan_source(src, session=Session(), delay=0)
    assert result.page_fetched is False
    assert result.access_blocked is False
    assert str(status) in result.errors[0]


def test_upstream_hosts_match_uscis_and_dhs_registry_allowlist():
    """403 soft-fail covers hosts those sources already use, and not DOL."""
    from src.ingestion.registry import SOURCE_REGISTRY

    for src in SOURCE_REGISTRY.values():
        if src.agency in ("USCIS", "DHS"):
            for host in src.allowed_hosts:
                assert is_known_upstream_host(host), (src.source_id, host)
        if src.agency == "DOL":
            for host in src.allowed_hosts:
                assert not is_known_upstream_host(host), (src.source_id, host)


def test_scan_source_dos_404_is_not_an_access_block():
    from src.ingestion.registry import get_source
    from src.ingestion.scanner import scan_source

    src = get_source("dos_iv_fsc")

    class Session:
        def get(self, *args, **kwargs):
            return _Resp(404, DOS_URL, reason="Not Found", body=b"missing")

    result = scan_source(src, session=Session(), delay=0)
    assert result.page_fetched is False
    assert result.access_blocked is False
    assert "404" in result.errors[0]


def test_fetch_dos_403_is_access_blocked(monkeypatch):
    from src.ingestion.fetcher import fetch_candidate
    from src.ingestion.scanner import RemoteCandidate

    dest = Path("data/DOS/_access_block_probe.xlsx")

    class Session:
        def get(self, *args, **kwargs):
            return _Resp(
                403,
                "https://travel.state.gov/content/dam/visas/Statistics/Immigrant-Statistics/MonthlyIVIssuances/FSC.xlsx",
                headers={"Server": "cloudflare", "CF-RAY": "ray"},
                body=b"Attention Required! | Cloudflare",
            )

    cand = RemoteCandidate(
        source_id="dos_iv_fsc",
        agency="DOS",
        url="https://travel.state.gov/content/dam/visas/Statistics/Immigrant-Statistics/MonthlyIVIssuances/FSC.xlsx",
        filename="_access_block_probe.xlsx",
        status="new",
        content_type="file",
        target_path=dest,
    )
    monkeypatch.setattr("src.ingestion.fetcher.is_under_data_dir", lambda p: True)
    result = fetch_candidate(cand, session=Session(), delay=0)
    assert result.success is False
    assert result.access_blocked is True
    assert result.error.startswith("UPSTREAM ACCESS BLOCKED:")
    assert dest.exists() is False


def _stub_validate_ok(monkeypatch):
    from src.ingestion.validator import ValidationReport
    from src.scripts import scan_and_pr as cli

    monkeypatch.setattr(cli, "validate_downloaded_files", lambda *a, **k: ValidationReport())


def _block_pr(monkeypatch):
    from src.scripts import scan_and_pr as cli

    def _no(**kwargs):
        raise AssertionError("create_data_pr must not run")

    monkeypatch.setattr(cli, "create_data_pr", _no)


def test_cli_legacy_dos_403_with_nothing_new_exits_0(monkeypatch, capsys):
    """Visa Bulletin run shape: only DOS source, 403, nothing to ingest → green."""
    from src.scripts import scan_and_pr as cli

    blocked = ScanResult(source_id="visa_bulletin", scan_url=VB_URL, page_fetched=False)
    blocked.errors.append(LEGACY_VB_403)
    monkeypatch.setattr(cli, "scan_sources", lambda *a, **k: [blocked])
    _stub_validate_ok(monkeypatch)
    _block_pr(monkeypatch)

    rc = cli.main(
        ["--scan", "--fetch", "--validate", "--pr", "--source", "visa_bulletin"]
    )
    captured = capsys.readouterr()
    assert rc == 0
    assert "UPSTREAM ACCESS BLOCKED" in captured.err
    assert "not a scanner bug" in captured.err
    assert "No new data to PR" in captured.out
    assert "unexpected source scan failure" not in captured.err


def test_cli_dos_block_plus_quiet_sources_exits_0(monkeypatch, capsys):
    """Data-source run shape when every reachable source is already up to date."""
    from src.scripts import scan_and_pr as cli

    dos = ScanResult(source_id="dos_iv_fsc", scan_url=DOS_URL, page_fetched=False)
    dos.errors.append(LEGACY_DOS_403)
    uscis = ScanResult(source_id="uscis_i140", scan_url=USCIS_URL, page_fetched=True)
    monkeypatch.setattr(cli, "scan_sources", lambda *a, **k: [dos, uscis])
    _stub_validate_ok(monkeypatch)
    _block_pr(monkeypatch)

    rc = cli.main(["--scan", "--fetch", "--validate", "--pr", "--source", "all"])
    captured = capsys.readouterr()
    assert rc == 0
    assert "UPSTREAM ACCESS BLOCKED" in captured.err
    assert "[BLOCKED] dos_iv_fsc" in captured.out
    assert "[OK] uscis_i140" in captured.out


def test_cli_dos_block_still_opens_pr_when_other_fetch_works(monkeypatch, capsys):
    from src.ingestion.fetcher import FetchResult
    from src.ingestion.pr_helper import PRResult
    from src.ingestion.scanner import RemoteCandidate
    from src.scripts import scan_and_pr as cli

    dos = ScanResult(source_id="dos_iv_fsc", scan_url=DOS_URL, page_fetched=False)
    dos.errors.append(LEGACY_DOS_403)
    uscis = ScanResult(source_id="uscis_i140", scan_url=USCIS_URL, page_fetched=True)
    cand = RemoteCandidate(
        source_id="uscis_i140",
        agency="USCIS",
        url="https://www.uscis.gov/sites/default/files/document/data/i140_fy2026_q3_v1.xlsx",
        filename="i140_fy2026_q3_v1.xlsx",
        status="new",
        content_type="file",
        target_path=Path("data/i140_fy2026_q3_v1.xlsx"),
    )
    uscis.candidates.append(cand)
    fetched = FetchResult(
        candidate=cand,
        success=True,
        path=Path("data/i140_fy2026_q3_v1.xlsx"),
        bytes_written=20,
    )
    called = {}

    def fake_pr(**kwargs):
        called["files"] = list(kwargs.get("files") or [])
        return PRResult(success=True, branch="chore/data-x", message="PR created", pr_url="https://example/pr/1")

    monkeypatch.setattr(cli, "scan_sources", lambda *a, **k: [dos, uscis])
    monkeypatch.setattr(cli, "fetch_from_scan_results", lambda *a, **k: [fetched])
    monkeypatch.setattr(cli, "paths_from_fetch_results", lambda *a, **k: ["data/i140_fy2026_q3_v1.xlsx"])
    monkeypatch.setattr(cli, "create_data_pr", fake_pr)
    _stub_validate_ok(monkeypatch)

    rc = cli.main(["--scan", "--fetch", "--validate", "--pr", "--source", "all"])
    captured = capsys.readouterr()
    assert rc == 0
    assert called["files"] == ["data/i140_fy2026_q3_v1.xlsx"]
    assert "UPSTREAM ACCESS BLOCKED" in captured.err
    assert "pr_url=https://example/pr/1" in captured.out


def test_cli_unexpected_scan_error_still_exits_1(monkeypatch, capsys):
    from src.scripts import scan_and_pr as cli

    bad = ScanResult(source_id="uscis_i140", scan_url=USCIS_URL, page_fetched=False)
    bad.errors.append("ConnectionError: down")
    monkeypatch.setattr(cli, "scan_sources", lambda *a, **k: [bad])
    _block_pr(monkeypatch)

    rc = cli.main(["--scan", "--fetch", "--pr", "--source", "uscis"])
    err = capsys.readouterr().err
    assert rc == 1
    assert "unexpected source scan failure" in err
    assert "ConnectionError: down" in err


def _blocked_scan(source_id: str, url: str, error: str) -> ScanResult:
    result = ScanResult(source_id=source_id, scan_url=url, page_fetched=False)
    result.errors.append(error)
    return result


def test_cli_run_42107407094_uscis_dhs_403s_exit_0(monkeypatch, capsys):
    """Scheduled `all` scan: only DOS/USCIS/DHS 403s must not exit 1 or open a PR.

    Mirrors run 42107407094: dos_iv_fsc already soft-failed, and the USCIS
    sources plus dhs_yearbook returned plain HTTP 403 with access_blocked false.
    """
    from src.scripts import scan_and_pr as cli

    scans = [
        _blocked_scan("dos_iv_fsc", DOS_URL, LEGACY_DOS_403),
        _blocked_scan("uscis_inventory", USCIS_URL, RUN_42107407094_USCIS_403),
        _blocked_scan("uscis_i485_perf", USCIS_URL, RUN_42107407094_USCIS_403),
        _blocked_scan("uscis_i140", USCIS_URL, RUN_42107407094_USCIS_403),
        _blocked_scan("dhs_yearbook", DHS_URL, RUN_42107407094_DHS_403),
        _blocked_scan("uscis_i485_monthly_csv", USCIS_URL, RUN_42107407094_USCIS_403),
    ]
    monkeypatch.setattr(cli, "scan_sources", lambda *a, **k: scans)
    _stub_validate_ok(monkeypatch)
    _block_pr(monkeypatch)

    rc = cli.main(
        ["--scan", "--fetch", "--validate", "--pr", "--source", "all", "--json"]
    )
    captured = capsys.readouterr()
    assert rc == 0
    assert "unexpected source scan failure" not in captured.err
    assert "UPSTREAM ACCESS BLOCKED" in captured.err
    assert "not a scanner bug" in captured.err
    for source_id in (
        "dos_iv_fsc",
        "uscis_inventory",
        "uscis_i485_perf",
        "uscis_i140",
        "dhs_yearbook",
        "uscis_i485_monthly_csv",
    ):
        assert f"[BLOCKED] {source_id}" in captured.out
    assert "No new data to PR" in captured.out
    payload = json.loads(captured.out[captured.out.rfind("\n{"):])
    assert payload["exit_hints"] == [
        "upstream_access_blocked",
        "nothing_new_after_access_block",
    ]
    assert payload["access_blocked_sources"] == [s.source_id for s in scans]
    assert "scan_failed" not in payload["exit_hints"]
    assert payload["pr"]["skipped"] is True


def test_cli_uscis_403_alone_exits_0(monkeypatch, capsys):
    from src.scripts import scan_and_pr as cli

    monkeypatch.setattr(
        cli,
        "scan_sources",
        lambda *a, **k: [_blocked_scan("uscis_i140", USCIS_URL, RUN_42107407094_USCIS_403)],
    )
    _stub_validate_ok(monkeypatch)
    _block_pr(monkeypatch)

    rc = cli.main(["--scan", "--fetch", "--validate", "--pr", "--source", "uscis_i140"])
    err = capsys.readouterr().err
    assert rc == 0
    assert "UPSTREAM ACCESS BLOCKED" in err
    assert "unexpected source scan failure" not in err


def test_cli_dhs_403_alone_exits_0(monkeypatch, capsys):
    from src.scripts import scan_and_pr as cli

    monkeypatch.setattr(
        cli,
        "scan_sources",
        lambda *a, **k: [_blocked_scan("dhs_yearbook", DHS_URL, RUN_42107407094_DHS_403)],
    )
    _stub_validate_ok(monkeypatch)
    _block_pr(monkeypatch)

    rc = cli.main(["--scan", "--fetch", "--validate", "--pr", "--source", "dhs"])
    err = capsys.readouterr().err
    assert rc == 0
    assert "UPSTREAM ACCESS BLOCKED" in err
    assert "unexpected source scan failure" not in err


def test_cli_dol_403_still_exits_1(monkeypatch, capsys):
    from src.scripts import scan_and_pr as cli

    bad = _blocked_scan("dol_perm", DOL_URL, _http_error(403, DOL_URL))
    monkeypatch.setattr(cli, "scan_sources", lambda *a, **k: [bad])
    _block_pr(monkeypatch)

    rc = cli.main(["--scan", "--fetch", "--pr", "--source", "dol"])
    err = capsys.readouterr().err
    assert rc == 1
    assert "unexpected source scan failure" in err
    assert "UPSTREAM ACCESS BLOCKED" not in err


def test_cli_uscis_404_still_exits_1(monkeypatch, capsys):
    from src.scripts import scan_and_pr as cli

    bad = _blocked_scan("uscis_i140", USCIS_URL, _http_error(404, USCIS_URL, "Not Found"))
    monkeypatch.setattr(cli, "scan_sources", lambda *a, **k: [bad])
    _block_pr(monkeypatch)

    rc = cli.main(["--scan", "--fetch", "--pr", "--source", "uscis"])
    err = capsys.readouterr().err
    assert rc == 1
    assert "unexpected source scan failure" in err
    assert "UPSTREAM ACCESS BLOCKED" not in err


def test_cli_uscis_403_plus_dhs_timeout_still_exits_1(monkeypatch, capsys):
    from src.scripts import scan_and_pr as cli

    uscis = _blocked_scan("uscis_inventory", USCIS_URL, RUN_42107407094_USCIS_403)
    bad = _blocked_scan("dhs_yearbook", DHS_URL, "Timeout: timed out")
    monkeypatch.setattr(cli, "scan_sources", lambda *a, **k: [uscis, bad])
    _block_pr(monkeypatch)

    rc = cli.main(["--scan", "--fetch", "--pr", "--source", "all"])
    err = capsys.readouterr().err
    assert rc == 1
    assert "UPSTREAM ACCESS BLOCKED" in err
    assert "unexpected source scan failure" in err
    assert "Timeout: timed out" in err


def test_cli_mixed_block_and_unexpected_exits_1_without_pr(monkeypatch, capsys):
    from src.scripts import scan_and_pr as cli

    dos = ScanResult(source_id="dos_iv_fsc", scan_url=DOS_URL, page_fetched=False)
    dos.errors.append(LEGACY_DOS_403)
    bad = ScanResult(source_id="dhs_yearbook", scan_url="https://ohss.dhs.gov/topics/immigration/yearbook", page_fetched=False)
    bad.errors.append("Timeout: timed out")
    monkeypatch.setattr(cli, "scan_sources", lambda *a, **k: [dos, bad])
    _block_pr(monkeypatch)

    rc = cli.main(["--scan", "--fetch", "--pr", "--source", "all"])
    err = capsys.readouterr().err
    assert rc == 1
    assert "UPSTREAM ACCESS BLOCKED" in err
    assert "unexpected source scan failure" in err
    assert "Timeout: timed out" in err


def test_cli_allow_scan_errors_still_exits_0_for_unexpected(monkeypatch):
    from src.scripts import scan_and_pr as cli

    bad = ScanResult(source_id="dos_iv_fsc", scan_url=DOS_URL, page_fetched=False)
    bad.errors.append("ConnectionError: down")
    monkeypatch.setattr(cli, "scan_sources", lambda *a, **k: [bad])
    rc = cli.main(["--scan", "--source", "dos_iv", "--allow-scan-errors"])
    assert rc == 0


def test_cli_fetch_access_block_with_nothing_else_exits_0(monkeypatch, capsys):
    from src.ingestion.fetcher import FetchResult
    from src.ingestion.scanner import RemoteCandidate
    from src.scripts import scan_and_pr as cli

    sr = ScanResult(source_id="dos_iv_fsc", scan_url=DOS_URL, page_fetched=True)
    cand = RemoteCandidate(
        source_id="dos_iv_fsc",
        agency="DOS",
        url="https://travel.state.gov/file.xlsx",
        filename="file.xlsx",
        status="new",
        content_type="file",
        target_path=Path("data/DOS/file.xlsx"),
    )
    sr.candidates.append(cand)
    blocked_fetch = FetchResult(
        candidate=cand,
        success=False,
        access_blocked=True,
        error=(
            "UPSTREAM ACCESS BLOCKED: dos_iv_fsc — HTTP 403 Cloudflare block. "
            "URL: https://travel.state.gov/file.xlsx."
        ),
    )
    monkeypatch.setattr(cli, "scan_sources", lambda *a, **k: [sr])
    monkeypatch.setattr(cli, "fetch_from_scan_results", lambda *a, **k: [blocked_fetch])
    _stub_validate_ok(monkeypatch)
    _block_pr(monkeypatch)

    rc = cli.main(["--scan", "--fetch", "--validate", "--pr", "--source", "dos_iv"])
    captured = capsys.readouterr()
    assert rc == 0
    assert "UPSTREAM ACCESS BLOCKED" in captured.err
    assert "No new data to PR" in captured.out


@pytest.mark.parametrize(
    "source_id,agency,url,filename",
    [
        (
            "uscis_i140",
            "USCIS",
            "https://www.uscis.gov/sites/default/files/document/data/i140_fy2026_q3_v1.xlsx",
            "_access_block_probe_uscis.xlsx",
        ),
        (
            "dhs_yearbook",
            "DHS",
            "https://ohss.dhs.gov/sites/default/files/2024-11/2023_yearbook_immigration_statistics.xlsx",
            "_access_block_probe_dhs.xlsx",
        ),
    ],
)
def test_fetch_uscis_dhs_403_is_access_blocked(monkeypatch, source_id, agency, url, filename):
    from src.ingestion.fetcher import fetch_candidate
    from src.ingestion.scanner import RemoteCandidate

    dest = Path("data") / filename

    class Session:
        def get(self, *args, **kwargs):
            return _Resp(403, url, body=b"Forbidden")

    cand = RemoteCandidate(
        source_id=source_id,
        agency=agency,
        url=url,
        filename=filename,
        status="new",
        content_type="file",
        target_path=dest,
    )
    monkeypatch.setattr("src.ingestion.fetcher.is_under_data_dir", lambda p: True)
    result = fetch_candidate(cand, session=Session(), delay=0)
    assert result.success is False
    assert result.access_blocked is True
    assert result.error.startswith("UPSTREAM ACCESS BLOCKED:")
    assert dest.exists() is False


def test_fetch_uscis_500_is_not_access_blocked(monkeypatch):
    from src.ingestion.fetcher import fetch_candidate
    from src.ingestion.scanner import RemoteCandidate

    url = "https://www.uscis.gov/sites/default/files/document/data/i140.xlsx"
    dest = Path("data/_access_block_probe_uscis_500.xlsx")

    class Session:
        def get(self, *args, **kwargs):
            return _Resp(500, url, reason="Server Error", body=b"nope")

    cand = RemoteCandidate(
        source_id="uscis_i140",
        agency="USCIS",
        url=url,
        filename=dest.name,
        status="new",
        content_type="file",
        target_path=dest,
    )
    monkeypatch.setattr("src.ingestion.fetcher.is_under_data_dir", lambda p: True)
    result = fetch_candidate(cand, session=Session(), delay=0)
    assert result.success is False
    assert result.access_blocked is False
    assert "500" in result.error


def test_cli_hard_fetch_failure_still_refuses_pr(monkeypatch, capsys):
    from src.ingestion.fetcher import FetchResult
    from src.ingestion.scanner import RemoteCandidate
    from src.scripts import scan_and_pr as cli

    sr = ScanResult(source_id="uscis_i140", scan_url=USCIS_URL, page_fetched=True)
    cand = RemoteCandidate(
        source_id="uscis_i140",
        agency="USCIS",
        url="https://www.uscis.gov/file.xlsx",
        filename="file.xlsx",
        status="new",
        content_type="file",
        target_path=Path("data/file.xlsx"),
    )
    sr.candidates.append(cand)
    monkeypatch.setattr(cli, "scan_sources", lambda *a, **k: [sr])
    monkeypatch.setattr(
        cli,
        "fetch_from_scan_results",
        lambda *a, **k: [FetchResult(candidate=cand, success=False, error="HTTPError: 500 Server Error")],
    )
    _block_pr(monkeypatch)

    rc = cli.main(["--scan", "--fetch", "--pr", "--source", "uscis"])
    err = capsys.readouterr().err
    assert rc == 1
    assert "all fetches failed" in err


def test_cli_validation_failure_still_blocks_when_dos_is_blocked(monkeypatch, capsys):
    from src.ingestion.scanner import RemoteCandidate
    from src.ingestion.validator import ValidationItem, ValidationReport
    from src.scripts import scan_and_pr as cli

    dos = ScanResult(source_id="dos_iv_fsc", scan_url=DOS_URL, page_fetched=False)
    dos.errors.append(LEGACY_DOS_403)
    uscis = ScanResult(source_id="uscis_i140", scan_url=USCIS_URL, page_fetched=True)
    cand = RemoteCandidate(
        source_id="uscis_i140",
        agency="USCIS",
        url="https://www.uscis.gov/file.xlsx",
        filename="file.xlsx",
        status="new",
        content_type="file",
        target_path=Path("data/file.xlsx"),
    )
    uscis.candidates.append(cand)
    bad = ValidationReport()
    bad.items.append(ValidationItem(path="data/file.xlsx", kind="pipeline", ok=False, message="corrupt"))

    monkeypatch.setattr(cli, "scan_sources", lambda *a, **k: [dos, uscis])
    monkeypatch.setattr(cli, "fetch_from_scan_results", lambda *a, **k: [])
    monkeypatch.setattr(cli, "validate_downloaded_files", lambda *a, **k: bad)
    _block_pr(monkeypatch)

    rc = cli.main(["--scan", "--fetch", "--validate", "--pr", "--source", "all"])
    err = capsys.readouterr().err
    assert rc == 1
    assert "validation failed" in err
