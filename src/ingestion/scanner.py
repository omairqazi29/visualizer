"""Scan configured public data pages for new downloadable files."""

from __future__ import annotations

import hashlib
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple
from urllib.parse import urljoin, unquote

from .registry import (
    DATA_DIR,
    PROJECT_ROOT,
    REQUEST_DELAY_SEC,
    REQUEST_TIMEOUT_SEC,
    USER_AGENT,
    DataSource,
    get_source,
    list_sources,
    resolve_source_ids,
    target_path_for,
)

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

    @property
    def new_candidates(self) -> List[RemoteCandidate]:
        return [c for c in self.candidates if c.status == "new"]

    @property
    def existing_candidates(self) -> List[RemoteCandidate]:
        return [c for c in self.candidates if c.status == "exists"]

    def to_dict(self) -> dict:
        return {
            "source_id": self.source_id,
            "scan_url": self.scan_url,
            "links_examined": self.links_examined,
            "page_fetched": self.page_fetched,
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
    """Extract (absolute_url, link_text) pairs from HTML.

    Uses regex (stdlib) so we don't require beautifulsoup4 at runtime,
    though tests may mock at the HTTP layer.
    """
    seen: Set[str] = set()
    out: List[Tuple[str, str]] = []

    for m in _HREF_RE.finditer(html or ""):
        href, inner = m.group(1), m.group(2)
        if not href or href.startswith(("#", "javascript:", "mailto:")):
            continue
        abs_url = urljoin(base_url, href)
        text = _strip_tags(inner)
        key = abs_url
        if key in seen:
            continue
        seen.add(key)
        out.append((abs_url, text))

    # Also catch hrefs without easily-parsed anchor body (e.g. split tags)
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
    hay = f"{url} {link_text}"
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


def _fuzzy_local_match(dedup: str, local_index: Dict[str, Path]) -> Optional[Path]:
    """Return a local path if dedup shares a strong stem with an existing file key.

    Handles minor USCIS naming drift (performance_data vs performancedata,
    optional _v1, optional extra underscore segments) without treating unrelated
    files as duplicates.
    """
    if not dedup or not local_index:
        return None
    # Compare core tokens: form id + fy/q when present
    def _core_tokens(key: str) -> Set[str]:
        parts = re.split(r"[_\-\s.]+", key.lower())
        keep = {p for p in parts if p and p not in {"xlsx", "xls", "data", "v1", "v2", "v3"}}
        return keep

    remote_toks = _core_tokens(dedup)
    if len(remote_toks) < 2:
        return None
    for lkey, lpath in local_index.items():
        local_toks = _core_tokens(lkey)
        if not local_toks:
            continue
        # Require substantial overlap and same primary form prefix when present
        inter = remote_toks & local_toks
        if len(inter) < 3:
            continue
        # If both mention fyYYYY/qN, those must match
        r_fy = {t for t in remote_toks if re.fullmatch(r"fy\d{4}", t)}
        l_fy = {t for t in local_toks if re.fullmatch(r"fy\d{4}", t)}
        if r_fy and l_fy and r_fy != l_fy:
            continue
        r_q = {t for t in remote_toks if re.fullmatch(r"q\d", t)}
        l_q = {t for t in local_toks if re.fullmatch(r"q\d", t)}
        if r_q and l_q and r_q != l_q:
            continue
        return lpath
    return None


def _file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _fetch_html(
    url: str,
    session=None,
    delay: float = REQUEST_DELAY_SEC,
    dry_run: bool = False,
) -> Tuple[Optional[str], Optional[str]]:
    """Return (html, error). dry_run still fetches for scan (read-only)."""
    if requests is None:
        return None, "requests library not installed"
    sess = session or requests.Session()
    headers = {"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml,*/*"}
    try:
        if delay and delay > 0:
            time.sleep(min(delay, 0.05) if dry_run else delay)  # tiny delay in dry_run for tests speed
        resp = sess.get(url, headers=headers, timeout=REQUEST_TIMEOUT_SEC)
        resp.raise_for_status()
        return resp.text, None
    except Exception as e:  # noqa: BLE001 — surface scan errors cleanly
        return None, f"{type(e).__name__}: {e}"


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

    if html_override is not None:
        html = html_override
        result.page_fetched = True
    else:
        html, err = _fetch_html(source.scan_url, session=session, delay=delay, dry_run=dry_run)
        if err:
            result.errors.append(err)
            return result
        result.page_fetched = True

    links = extract_links(html, source.scan_url)
    result.links_examined = len(links)

    target_dir = PROJECT_ROOT / source.target_dir
    local_index = _local_files_index(target_dir, source.dedup_key_fn)

    # Visa bulletin is special: track bulletin HTML URLs, not binary downloads
    is_bulletin = source.source_id == "visa_bulletin"
    # Only flag recent bulletins as actionable (avoid 20+ years of archive links)
    from datetime import datetime, timezone

    vb_min_year = datetime.now(timezone.utc).year - 1  # current + previous calendar year

    seen_dedup: Set[str] = set()

    for url, text in links:
        if is_bulletin:
            if not _patterns_match(url, text, source.link_patterns):
                continue
            # Only actual bulletin pages
            if not re.search(r"visa-bulletin-for-", url, re.I):
                continue
            filename = unquote(url.rstrip("/").split("/")[-1])
            # Extract year from path or filename (.../2026/visa-bulletin-for-june-2026.html)
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

            # Track seen bulletins via a small sidecar list if present
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
                    # Also index by basename so either full URL or filename works
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

        filename = source.normalize_fn(url, text)
        if not filename:
            continue
        dedup = source.dedup_key_fn(filename)
        if dedup in seen_dedup:
            continue
        seen_dedup.add(dedup)

        dest = target_path_for(source, filename)
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

        if dedup in local_index:
            cand.status = "exists"
            cand.reason = f"local file present: {local_index[dedup].name}"
        elif dest.exists():
            cand.status = "exists"
            cand.reason = f"target path exists: {dest.name}"
        else:
            # Secondary fuzzy only for USCIS (performance_data vs performancedata, etc.)
            # DOS month files share too many tokens (IV/Issuances/FSC) to fuzzy-match safely.
            fuzzy_hit = None
            if source.agency == "USCIS":
                fuzzy_hit = _fuzzy_local_match(dedup, local_index)
            if fuzzy_hit is not None:
                cand.status = "exists"
                cand.reason = f"fuzzy match local file: {fuzzy_hit.name}"
            else:
                cand.status = "new"
                cand.reason = "not found in target directory"
        result.candidates.append(cand)

    # Sort: new first, then by filename
    result.candidates.sort(key=lambda c: (0 if c.status == "new" else 1, c.filename))
    return result


def scan_sources(
    source_ids: Optional[Sequence[str]] = None,
    *,
    session=None,
    delay: float = REQUEST_DELAY_SEC,
    dry_run: bool = False,
) -> List[ScanResult]:
    """Scan multiple sources (default: all enabled)."""
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
    for r in results:
        n_new = len(r.new_candidates)
        n_ex = len(r.existing_candidates)
        total_new += n_new
        total_exist += n_ex
        status = "OK" if r.page_fetched else "FAIL"
        lines.append(
            f"[{status}] {r.source_id}: {n_new} new, {n_ex} already present "
            f"({r.links_examined} links, {len(r.errors)} errors)"
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
    return "\n".join(lines)
