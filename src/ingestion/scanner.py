"""Scan configured public data pages for new downloadable files."""

from __future__ import annotations

import hashlib
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Set, Tuple
from urllib.parse import urljoin, urlparse, unquote

from .registry import (
    PROJECT_ROOT,
    REQUEST_DELAY_SEC,
    REQUEST_TIMEOUT_SEC,
    USER_AGENT,
    DataSource,
    get_source,
    list_sources,
    target_path_for,
    uscis_names_equivalent,
)
from .security import is_allowed_url, safe_basename

try:
    import requests
except ImportError:  # pragma: no cover
    requests = None  # type: ignore


@dataclass
class RemoteCandidate:
    """A remote file (or bulletin page) discovered during scan."""

    source_id: str
    agency: str
    url: str
    filename: str
    link_text: str = ""
    target_path: Optional[Path] = None
    status: str = "new"  # new | exists | skipped | error
    reason: str = ""
    content_type: str = ""  # file | bulletin_page
    dedup_key: str = ""

    def to_dict(self) -> dict:
        return {
            "source_id": self.source_id,
            "agency": self.agency,
            "url": self.url,
            "filename": self.filename,
            "link_text": self.link_text,
            "target_path": str(self.target_path) if self.target_path else None,
            "status": self.status,
            "reason": self.reason,
            "content_type": self.content_type,
            "dedup_key": self.dedup_key,
        }


@dataclass
class ScanResult:
    source_id: str
    scan_url: str
    candidates: List[RemoteCandidate] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    links_examined: int = 0
    page_fetched: bool = False
    pages_scanned: int = 0

    @property
    def new_candidates(self) -> List[RemoteCandidate]:
        return [c for c in self.candidates if c.status == "new"]

    @property
    def existing_candidates(self) -> List[RemoteCandidate]:
        return [c for c in self.candidates if c.status == "exists"]

    @property
    def failed(self) -> bool:
        return bool(self.errors) and not self.page_fetched

    def to_dict(self) -> dict:
        return {
            "source_id": self.source_id,
            "scan_url": self.scan_url,
            "links_examined": self.links_examined,
            "page_fetched": self.page_fetched,
            "pages_scanned": self.pages_scanned,
            "errors": self.errors,
            "new_count": len(self.new_candidates),
            "existing_count": len(self.existing_candidates),
            "candidates": [c.to_dict() for c in self.candidates],
        }


_HREF_RE = re.compile(
    r"""<a\s[^>]*?href\s*=\s*["']([^"']+)["'][^>]*>(.*?)</a>""",
    re.I | re.S,
)
_HREF_ONLY_RE = re.compile(r"""href\s*=\s*["']([^"']+)["']""", re.I)
_TAG_RE = re.compile(r"<[^>]+>")


def _strip_tags(html_fragment: str) -> str:
    text = _TAG_RE.sub(" ", html_fragment or "")
    return " ".join(text.split())


def extract_links(html: str, base_url: str) -> List[Tuple[str, str]]:
    """Extract (absolute_url, link_text) pairs from HTML (stdlib regex)."""
    seen: Set[str] = set()
    out: List[Tuple[str, str]] = []

    for m in _HREF_RE.finditer(html or ""):
        href, inner = m.group(1), m.group(2)
        if not href or href.startswith(("#", "javascript:", "mailto:")):
            continue
        abs_url = urljoin(base_url, href)
        text = _strip_tags(inner)
        if abs_url in seen:
            continue
        seen.add(abs_url)
        out.append((abs_url, text))

    for m in _HREF_ONLY_RE.finditer(html or ""):
        href = m.group(1)
        if not href or href.startswith(("#", "javascript:", "mailto:")):
            continue
        abs_url = urljoin(base_url, href)
        if abs_url in seen:
            continue
        seen.add(abs_url)
        out.append((abs_url, ""))

    return out


def _ext_matches(url: str, extensions: Sequence[str]) -> bool:
    path = unquote(url.split("?")[0].lower())
    return any(path.endswith(ext) for ext in extensions)


def _patterns_match(url: str, link_text: str, patterns: Sequence[str]) -> bool:
    # Unquote URL so %20 spaces match patterns like "IV Issuances by FSC"
    hay = f"{unquote(url)} {link_text}"
    for pat in patterns:
        if re.search(pat, hay, re.I):
            return True
    return False


def _local_files_index(target_dir: Path, dedup_key_fn) -> Dict[str, Path]:
    """Map dedup_key -> existing local path for files in target_dir."""
    index: Dict[str, Path] = {}
    if not target_dir.exists():
        return index
    for p in target_dir.iterdir():
        if p.is_file() and not p.name.startswith("."):
            index[dedup_key_fn(p.name)] = p
    return index


def _uscis_local_match(filename: str, local_index: Dict[str, Path], dedup_key_fn) -> Optional[Path]:
    """Match only via normalized dedup key (performance_data variants / _vN), not fuzzy tokens."""
    key = dedup_key_fn(filename)
    if key in local_index:
        return local_index[key]
    # Also try direct name equivalence walk for safety
    for lkey, lpath in local_index.items():
        if uscis_names_equivalent(filename, lpath.name):
            return lpath
    return None


def _fetch_html(
    url: str,
    source: DataSource,
    session=None,
    delay: float = REQUEST_DELAY_SEC,
) -> Tuple[Optional[str], Optional[str]]:
    """Return (html, error). Validates host allowlist."""
    ok, reason = is_allowed_url(url, source.allowed_hosts or ())
    if not ok:
        return None, f"url blocked: {reason} ({url[:80]})"

    if requests is None:
        return None, "requests library not installed"
    sess = session or requests.Session()
    headers = {"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml,*/*"}
    try:
        if delay and delay > 0:
            time.sleep(delay)
        resp = sess.get(url, headers=headers, timeout=REQUEST_TIMEOUT_SEC, allow_redirects=True)
        resp.raise_for_status()
        # Validate final URL after redirects
        final_ok, final_reason = is_allowed_url(resp.url, source.allowed_hosts or ())
        if not final_ok:
            return None, f"redirect blocked: {final_reason} ({resp.url[:80]})"
        return resp.text, None
    except Exception as e:  # noqa: BLE001
        return None, f"{type(e).__name__}: {e}"


def _collect_pages_html(
    source: DataSource,
    *,
    session=None,
    delay: float = REQUEST_DELAY_SEC,
    html_override: Optional[str] = None,
) -> Tuple[List[Tuple[str, str]], List[str]]:
    """Return [(page_url, html), ...] and errors. Optionally follows secondary links (depth 1)."""
    errors: List[str] = []
    pages: List[Tuple[str, str]] = []

    if html_override is not None:
        return [(source.scan_url, html_override)], errors

    html, err = _fetch_html(source.scan_url, source, session=session, delay=delay)
    if err:
        errors.append(err)
        return pages, errors
    pages.append((source.scan_url, html))

    if not source.follow_links or not source.secondary_page_patterns:
        return pages, errors

    # Depth-1 follow: same-host HTML pages matching secondary patterns
    primary_links = extract_links(html, source.scan_url)
    seen_pages = {source.scan_url}
    followed = 0
    max_follow = 8  # polite cap
    for url, text in primary_links:
        if followed >= max_follow:
            break
        if url in seen_pages:
            continue
        if not _patterns_match(url, text, source.secondary_page_patterns):
            continue
        # Only HTML-ish pages (not direct file downloads)
        if _ext_matches(url, (".xlsx", ".xls", ".pdf", ".zip", ".csv")):
            continue
        ok, _ = is_allowed_url(url, source.allowed_hosts or ())
        if not ok:
            continue
        # Same registrable host family only
        if urlparse(url).hostname and urlparse(source.scan_url).hostname:
            if urlparse(url).hostname.split(".")[-2:] != urlparse(source.scan_url).hostname.split(".")[-2:]:
                # allow if both in allowed_hosts
                pass
        sub_html, sub_err = _fetch_html(url, source, session=session, delay=delay)
        if sub_err:
            errors.append(f"secondary {url[:60]}: {sub_err}")
            continue
        seen_pages.add(url)
        pages.append((url, sub_html))
        followed += 1

    return pages, errors


def scan_source(
    source: DataSource,
    *,
    session=None,
    delay: float = REQUEST_DELAY_SEC,
    dry_run: bool = False,
    html_override: Optional[str] = None,
) -> ScanResult:
    """Scan one data source; classify candidates as new vs already present."""
    result = ScanResult(source_id=source.source_id, scan_url=source.scan_url)

    pages, fetch_errors = _collect_pages_html(
        source, session=session, delay=delay if not dry_run else min(delay, 0.05),
        html_override=html_override,
    )
    result.errors.extend(fetch_errors)
    if not pages:
        return result

    result.page_fetched = True
    result.pages_scanned = len(pages)

    all_links: List[Tuple[str, str]] = []
    for page_url, html in pages:
        all_links.extend(extract_links(html, page_url))
    result.links_examined = len(all_links)

    target_dir = PROJECT_ROOT / source.target_dir
    local_index = _local_files_index(target_dir, source.dedup_key_fn)
    is_bulletin = source.source_id == "visa_bulletin"
    vb_min_year = datetime.now(timezone.utc).year - 1

    seen_dedup: Set[str] = set()

    for url, text in all_links:
        # URL host allowlist for candidates
        ok_url, block_reason = is_allowed_url(url, source.allowed_hosts or ())
        if not ok_url:
            continue

        if is_bulletin:
            if not _patterns_match(url, text, source.link_patterns):
                continue
            if not re.search(r"visa-bulletin-for-", url, re.I):
                continue
            try:
                filename = safe_basename(unquote(url.rstrip("/").split("/")[-1]))
            except ValueError:
                continue
            year_m = re.search(r"/(\d{4})/visa-bulletin-for-", url) or re.search(
                r"visa-bulletin-for-\w+-(\d{4})", filename, re.I
            )
            if year_m:
                try:
                    if int(year_m.group(1)) < vb_min_year:
                        continue
                except ValueError:
                    pass
            dedup = filename.lower()
            if dedup in seen_dedup:
                continue
            seen_dedup.add(dedup)

            seen_file = target_dir / ".seen_bulletins.txt"
            known_urls: Set[str] = set()
            known_names: Set[str] = set()
            if seen_file.exists():
                for ln in seen_file.read_text().splitlines():
                    ln = ln.strip()
                    if not ln:
                        continue
                    low = ln.lower()
                    known_urls.add(low)
                    known_names.add(unquote(low.rstrip("/").split("/")[-1]))

            cand = RemoteCandidate(
                source_id=source.source_id,
                agency=source.agency,
                url=url,
                filename=filename,
                link_text=text,
                target_path=seen_file,
                content_type="bulletin_page",
                dedup_key=dedup,
            )
            if url.lower() in known_urls or dedup in known_names:
                cand.status = "exists"
                cand.reason = "bulletin URL already recorded in .seen_bulletins.txt"
            else:
                cand.status = "new"
                cand.reason = "new visa bulletin page — update india_eb_history.csv manually or via helper"
            result.candidates.append(cand)
            continue

        # File downloads
        if not _ext_matches(url, source.extensions):
            continue
        if not _patterns_match(url, text, source.link_patterns):
            continue

        try:
            raw_name = source.normalize_fn(url, text)
            filename = safe_basename(raw_name)
        except ValueError as e:
            continue

        dedup = source.dedup_key_fn(filename)
        if dedup in seen_dedup:
            continue
        seen_dedup.add(dedup)

        try:
            dest = target_path_for(source, filename)
        except ValueError as e:
            cand = RemoteCandidate(
                source_id=source.source_id,
                agency=source.agency,
                url=url,
                filename=filename,
                link_text=text,
                status="error",
                reason=str(e),
                content_type="file",
                dedup_key=dedup,
            )
            result.candidates.append(cand)
            continue

        cand = RemoteCandidate(
            source_id=source.source_id,
            agency=source.agency,
            url=url,
            filename=filename,
            link_text=text,
            target_path=dest,
            content_type="file",
            dedup_key=dedup,
        )

        if source.agency == "USCIS":
            hit = _uscis_local_match(filename, local_index, source.dedup_key_fn)
            if hit is not None:
                cand.status = "exists"
                cand.reason = f"local file present: {hit.name}"
            elif dest.exists():
                cand.status = "exists"
                cand.reason = f"target path exists: {dest.name}"
            else:
                cand.status = "new"
                cand.reason = "not found in target directory"
        else:
            if dedup in local_index:
                cand.status = "exists"
                cand.reason = f"local file present: {local_index[dedup].name}"
            elif dest.exists():
                cand.status = "exists"
                cand.reason = f"target path exists: {dest.name}"
            else:
                cand.status = "new"
                cand.reason = "not found in target directory"
        result.candidates.append(cand)

    result.candidates.sort(key=lambda c: (0 if c.status == "new" else 1, c.filename))
    return result


def scan_sources(
    source_ids: Optional[Sequence[str]] = None,
    *,
    session=None,
    delay: float = REQUEST_DELAY_SEC,
    dry_run: bool = False,
) -> List[ScanResult]:
    """Scan multiple sources (default: all enabled non-VB via caller resolve)."""
    if source_ids is None:
        sources = list_sources(enabled_only=True)
    else:
        sources = [get_source(sid) for sid in source_ids]

    results: List[ScanResult] = []
    for src in sources:
        if not src.enabled and source_ids is None:
            continue
        results.append(
            scan_source(src, session=session, delay=delay, dry_run=dry_run)
        )
    return results


def summarize_scan(results: List[ScanResult]) -> str:
    lines = ["=== Data Source Scan Summary ==="]
    total_new = 0
    total_exist = 0
    any_fail = False
    for r in results:
        n_new = len(r.new_candidates)
        n_ex = len(r.existing_candidates)
        total_new += n_new
        total_exist += n_ex
        status = "OK" if r.page_fetched else "FAIL"
        if not r.page_fetched:
            any_fail = True
        lines.append(
            f"[{status}] {r.source_id}: {n_new} new, {n_ex} already present "
            f"({r.links_examined} links, {r.pages_scanned} pages, {len(r.errors)} errors)"
        )
        if r.errors:
            for e in r.errors:
                lines.append(f"       error: {e}")
        for c in r.new_candidates[:12]:
            lines.append(f"       NEW: {c.filename}")
            lines.append(f"            {c.url[:100]}")
        if len(r.new_candidates) > 12:
            lines.append(f"       ... and {len(r.new_candidates) - 12} more new")
    lines.append(f"TOTAL: {total_new} new file(s)/bulletin(s), {total_exist} already present")
    if any_fail:
        lines.append("WARNING: one or more source scans failed (see errors above)")
    return "\n".join(lines)
