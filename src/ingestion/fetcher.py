"""Download newly discovered data files into the correct data/ paths."""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Sequence

from .registry import REQUEST_DELAY_SEC, REQUEST_TIMEOUT_SEC, USER_AGENT, get_source
from .scanner import RemoteCandidate, ScanResult
from .security import (
    MAX_DOWNLOAD_BYTES,
    is_allowed_url,
    is_under_data_dir,
    looks_like_html,
    looks_like_spreadsheet,
    safe_target_path,
)

try:
    import requests
except ImportError:  # pragma: no cover
    requests = None  # type: ignore


@dataclass
class FetchResult:
    candidate: RemoteCandidate
    success: bool
    path: Optional[Path] = None
    bytes_written: int = 0
    error: str = ""
    skipped: bool = False
    dry_run: bool = False

    def to_dict(self) -> dict:
        return {
            "source_id": self.candidate.source_id,
            "filename": self.candidate.filename,
            "url": self.candidate.url,
            "success": self.success,
            "skipped": self.skipped,
            "dry_run": self.dry_run,
            "path": str(self.path) if self.path else None,
            "bytes_written": self.bytes_written,
            "error": self.error,
        }


def _allowed_hosts_for(candidate: RemoteCandidate) -> Sequence[str]:
    try:
        return get_source(candidate.source_id).allowed_hosts or ()
    except KeyError:
        return ()


def fetch_candidate(
    candidate: RemoteCandidate,
    *,
    session=None,
    delay: float = REQUEST_DELAY_SEC,
    dry_run: bool = False,
    force: bool = False,
) -> FetchResult:
    """Download one candidate file. Bulletin pages are recorded, not downloaded as data."""
    if candidate.content_type == "bulletin_page":
        return _record_bulletin(candidate, dry_run=dry_run)

    if candidate.status == "exists" and not force:
        return FetchResult(
            candidate=candidate,
            success=True,
            skipped=True,
            path=candidate.target_path,
            error="already exists (skip)",
        )

    if candidate.status == "error":
        return FetchResult(
            candidate=candidate,
            success=False,
            error=candidate.reason or "candidate error status",
        )

    dest = candidate.target_path
    if dest is None:
        return FetchResult(candidate=candidate, success=False, error="no target_path")

    # Security: must land under data/
    if not is_under_data_dir(dest):
        return FetchResult(
            candidate=candidate,
            success=False,
            error=f"refusing to write outside data/: {dest}",
        )

    if dry_run:
        return FetchResult(
            candidate=candidate,
            success=True,
            dry_run=True,
            path=dest,
            error="dry-run: would download",
        )

    hosts = _allowed_hosts_for(candidate)
    ok, reason = is_allowed_url(candidate.url, hosts)
    if not ok:
        return FetchResult(candidate=candidate, success=False, error=f"url blocked: {reason}")

    if requests is None:
        return FetchResult(candidate=candidate, success=False, error="requests not installed")

    sess = session or requests.Session()
    headers = {"User-Agent": USER_AGENT, "Accept": "application/octet-stream,*/*"}
    tmp: Optional[Path] = None
    try:
        if delay and delay > 0:
            time.sleep(delay)
        resp = sess.get(
            candidate.url,
            headers=headers,
            timeout=REQUEST_TIMEOUT_SEC,
            stream=True,
            allow_redirects=True,
        )
        resp.raise_for_status()

        final_ok, final_reason = is_allowed_url(resp.url, hosts)
        if not final_ok:
            return FetchResult(
                candidate=candidate,
                success=False,
                error=f"redirect blocked: {final_reason}",
            )

        # Content-Length pre-check
        cl = resp.headers.get("Content-Length")
        if cl and cl.isdigit() and int(cl) > MAX_DOWNLOAD_BYTES:
            return FetchResult(
                candidate=candidate,
                success=False,
                error=f"Content-Length {cl} exceeds max {MAX_DOWNLOAD_BYTES}",
            )

        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_suffix(dest.suffix + ".part")
        size = 0
        first_chunk = b""
        with open(tmp, "wb") as f:
            for chunk in resp.iter_content(chunk_size=65536):
                if not chunk:
                    continue
                if size == 0:
                    first_chunk = chunk[:512]
                    if looks_like_html(first_chunk) and not candidate.filename.lower().endswith(
                        (".html", ".htm")
                    ):
                        raise ValueError("response looks like HTML, not a data file")
                    ext = dest.suffix.lower()
                    if ext in (".xlsx", ".xls") and not looks_like_spreadsheet(
                        first_chunk, candidate.filename
                    ):
                        # warn but allow if content-type suggests octet-stream and has length
                        ctype = (resp.headers.get("Content-Type") or "").lower()
                        if "html" in ctype or "text/html" in ctype:
                            raise ValueError(f"unexpected content-type for spreadsheet: {ctype}")
                size += len(chunk)
                if size > MAX_DOWNLOAD_BYTES:
                    raise ValueError(f"download exceeded max size {MAX_DOWNLOAD_BYTES} bytes")
                f.write(chunk)

        if size == 0:
            raise ValueError("empty download")

        tmp.replace(dest)
        tmp = None
        candidate.status = "fetched"
        return FetchResult(candidate=candidate, success=True, path=dest, bytes_written=size)
    except Exception as e:  # noqa: BLE001
        return FetchResult(candidate=candidate, success=False, error=f"{type(e).__name__}: {e}")
    finally:
        if tmp is not None and tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass


def _record_bulletin(candidate: RemoteCandidate, *, dry_run: bool = False) -> FetchResult:
    """Append bulletin URL to .seen_bulletins.txt (does not modify history CSVs)."""
    seen_file = candidate.target_path
    if seen_file is None:
        return FetchResult(candidate=candidate, success=False, error="no seen_file path")

    if candidate.status == "exists":
        return FetchResult(
            candidate=candidate,
            success=True,
            skipped=True,
            path=seen_file,
            error="bulletin already recorded",
        )

    if dry_run:
        return FetchResult(
            candidate=candidate,
            success=True,
            dry_run=True,
            path=seen_file,
            error="dry-run: would record bulletin URL",
        )

    try:
        seen_file.parent.mkdir(parents=True, exist_ok=True)
        with open(seen_file, "a", encoding="utf-8") as f:
            f.write(f"{candidate.url}\n")
        return FetchResult(
            candidate=candidate,
            success=True,
            path=seen_file,
            bytes_written=len(candidate.url) + 1,
        )
    except Exception as e:  # noqa: BLE001
        return FetchResult(candidate=candidate, success=False, error=f"{type(e).__name__}: {e}")


def fetch_candidates(
    candidates: Sequence[RemoteCandidate],
    *,
    session=None,
    delay: float = REQUEST_DELAY_SEC,
    dry_run: bool = False,
    new_only: bool = True,
) -> List[FetchResult]:
    results: List[FetchResult] = []
    for cand in candidates:
        if new_only and cand.status not in ("new", "fetched"):
            continue
        if cand.content_type == "bulletin_page" and new_only and cand.status != "new":
            continue
        results.append(
            fetch_candidate(cand, session=session, delay=delay, dry_run=dry_run)
        )
    return results


def fetch_from_scan_results(
    scan_results: Sequence[ScanResult],
    *,
    session=None,
    delay: float = REQUEST_DELAY_SEC,
    dry_run: bool = False,
    new_only: bool = True,
) -> List[FetchResult]:
    all_cands: List[RemoteCandidate] = []
    for sr in scan_results:
        all_cands.extend(sr.candidates)
    return fetch_candidates(
        all_cands, session=session, delay=delay, dry_run=dry_run, new_only=new_only
    )


def any_fetch_failed(results: Sequence[FetchResult]) -> bool:
    """True if any non-skipped, non-dry-run fetch failed."""
    return any(not r.success and not r.skipped for r in results)


def summarize_fetch(results: List[FetchResult]) -> str:
    lines = ["=== Fetch Summary ==="]
    ok = sum(1 for r in results if r.success and not r.skipped and not r.dry_run)
    skipped = sum(1 for r in results if r.skipped)
    dry = sum(1 for r in results if r.dry_run)
    fail = sum(1 for r in results if not r.success)
    lines.append(f"downloaded={ok} skipped={skipped} dry_run={dry} failed={fail}")
    for r in results:
        tag = "OK" if r.success else "FAIL"
        if r.dry_run:
            tag = "DRY"
        if r.skipped:
            tag = "SKIP"
        lines.append(f"  [{tag}] {r.candidate.filename}: {r.error or r.path}")
    return "\n".join(lines)
