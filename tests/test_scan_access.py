"""DOS Cloudflare 403 classification and scan_and_pr exit behavior."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.ingestion.http_client import (
    classify_response,
    html_request_headers,
    is_upstream_access_block,
)
from src.ingestion.scanner import ScanResult, summarize_scan

VB_URL = "https://travel.state.gov/content/travel/en/legal/visa-law0/visa-bulletin.html"
DOS_URL = (
    "https://travel.state.gov/content/travel/en/legal/visa-law0/"
    "visa-statistics/immigrant-visa-statistics/monthly-immigrant-visa-issuances.html"
)
USCIS_URL = "https://www.uscis.gov/tools/reports-and-studies/immigration-and-citizenship-data"
LEGACY_VB_403 = (
    "HTTPError: 403 Client Error: Forbidden for url: " + VB_URL
)
LEGACY_DOS_403 = (
    "HTTPError: 403 Client Error: Forbidden for url: " + DOS_URL
)


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
            False,
            False,
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
    assert not is_upstream_access_block(
        "HTTPError: 404 Client Error: Not Found for url: " + VB_URL, VB_URL
    )
    assert not is_upstream_access_block(
        "HTTPError: 403 Client Error: Forbidden for url: " + USCIS_URL, USCIS_URL
    )
    assert not is_upstream_access_block("ConnectionError: down", DOS_URL)
    assert not is_upstream_access_block("Timeout: timed out", VB_URL)


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


def test_cli_non_dos_403_still_exits_1(monkeypatch, capsys):
    from src.scripts import scan_and_pr as cli

    bad = ScanResult(source_id="uscis_i140", scan_url=USCIS_URL, page_fetched=False)
    bad.errors.append("HTTPError: 403 Client Error: Forbidden for url: " + USCIS_URL)
    monkeypatch.setattr(cli, "scan_sources", lambda *a, **k: [bad])
    _block_pr(monkeypatch)

    rc = cli.main(["--scan", "--fetch", "--pr", "--source", "uscis"])
    err = capsys.readouterr().err
    assert rc == 1
    assert "unexpected source scan failure" in err
    assert "UPSTREAM ACCESS BLOCKED" not in err


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
