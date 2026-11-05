"""Request headers and upstream-access classification for public data scans.

``travel.state.gov`` sits behind Cloudflare. Datacenter clients, including
GitHub Actions, receive HTTP 403 pages titled "Attention Required! | Cloudflare"
(``Server: cloudflare`` plus a ``cf-ray`` header). The same runners also get
plain HTTP 403 Forbidden from the USCIS and DHS pages this scanner already
requests (``www.uscis.gov``, ``ohss.dhs.gov``). A realistic browser User-Agent
does not clear those refusals. This module sends ordinary browser headers and
classifies that response as an upstream access block so scheduled scans can
continue. It does not solve challenges, impersonate TLS fingerprints, or
replay cookies.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Mapping, Optional
from urllib.parse import urlparse

from .registry import USER_AGENT

# Hosts whose HTTP 403 (or Cloudflare 503 challenge) is an upstream block,
# not a scanner bug. DOL and every other host stay hard failures.
#
# DOS (travel.state.gov / ceac.state.gov): Cloudflare 403 from GitHub Actions.
# USCIS / DHS: the same runners get HTTP 403 Forbidden on the hosts those
# sources already allow in the registry (www.uscis.gov, egov.uscis.gov,
# ohss.dhs.gov, www.dhs.gov). Suffix match covers subdomains of the apex.
KNOWN_DOS_HOSTS = frozenset(
    {
        "travel.state.gov",
        "ceac.state.gov",
    }
)
KNOWN_USCIS_HOSTS = frozenset(
    {
        "uscis.gov",
    }
)
KNOWN_DHS_HOSTS = frozenset(
    {
        "dhs.gov",
        "ohss.dhs.gov",
    }
)
KNOWN_UPSTREAM_HOSTS = KNOWN_DOS_HOSTS | KNOWN_USCIS_HOSTS | KNOWN_DHS_HOSTS

_CF_BODY_MARKERS = (
    "attention required",
    "just a moment",
    "cloudflare",
    "challenge-platform",
    "sorry, you have been blocked",
    "cf-browser-verification",
)
_URL_RE = re.compile(r"https?://[^\s)>\"]+")
_STATUS_RE = re.compile(
    r"(?:HTTP(?:Error)?[:\s]+|status[:=\s]+)(\d{3})\b|\b(\d{3})\s+Client Error\b",
    re.I,
)


@dataclass(frozen=True)
class AccessBlock:
    """A fetch that failed because a known DOS, USCIS, or DHS host blocked the client."""

    url: str
    host: str
    status: int
    cloudflare: bool
    source_id: str = ""

    @property
    def message(self) -> str:
        return format_access_block(
            source_id=self.source_id,
            url=self.url,
            status=self.status,
            cloudflare=self.cloudflare,
            host=self.host,
        )


def html_request_headers() -> dict:
    """Headers for HTML index pages. Static browser-like values, not a bypass."""
    return {
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Cache-Control": "no-cache",
        "Upgrade-Insecure-Requests": "1",
    }


def download_request_headers() -> dict:
    """Headers for file downloads. Same UA as HTML fetches; no challenge logic."""
    return {
        "User-Agent": USER_AGENT,
        "Accept": (
            "application/octet-stream,"
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,"
            "*/*;q=0.8"
        ),
        "Accept-Language": "en-US,en;q=0.9",
        "Cache-Control": "no-cache",
    }


def hostname_of(url: str) -> str:
    try:
        return (urlparse(url).hostname or "").lower().rstrip(".")
    except Exception:  # noqa: BLE001
        return ""


def _host_in(host: str, known_hosts: frozenset) -> bool:
    host = (host or "").lower().rstrip(".")
    if not host:
        return False
    return any(host == known or host.endswith("." + known) for known in known_hosts)


def is_known_dos_host(host: str) -> bool:
    """True for travel.state.gov / ceac.state.gov (and their subdomains)."""
    return _host_in(host, KNOWN_DOS_HOSTS)


def is_known_upstream_host(host: str) -> bool:
    """True for DOS, USCIS, and DHS hosts whose HTTP 403 is an access block."""
    return _host_in(host, KNOWN_UPSTREAM_HOSTS)


def looks_like_cloudflare(headers: Optional[Mapping] = None, body: str = "") -> bool:
    """True when response headers or a short body snippet show a CF challenge."""
    lowered = _header_map(headers)
    if "cf-ray" in lowered or "cf-mitigated" in lowered:
        return True
    if "cloudflare" in lowered.get("server", ""):
        return True
    text = (body or "").lower()
    return any(marker in text for marker in _CF_BODY_MARKERS)


def format_access_block(
    *,
    source_id: str = "",
    url: str,
    status: int,
    cloudflare: bool,
    host: str = "",
) -> str:
    """Operator-facing explanation when a known upstream host is still blocked."""
    host = host or hostname_of(url) or "known upstream host"
    who = source_id or host
    if cloudflare:
        kind = (
            f"HTTP {status} Cloudflare block "
            f"(Server: cloudflare / challenge page on {host})"
        )
        advice = "A browser User-Agent does not clear the Cloudflare challenge. "
    else:
        kind = f"HTTP {status} Forbidden on known upstream host {host}"
        advice = ""
    return (
        f"UPSTREAM ACCESS BLOCKED: {who} — {kind}. "
        f"URL: {url}. "
        f"No new files were ingested for this source. "
        f"This is an upstream access block, not a broken scanner URL or a validation error. "
        f"{advice}"
        f"Drop the file under data/ manually, or re-run from a network that can reach {host}."
    )


def classify_response(
    *,
    url: str,
    status: Optional[int],
    headers: Optional[Mapping] = None,
    body: str = "",
    source_id: str = "",
) -> Optional[AccessBlock]:
    """Return an AccessBlock for known-host 403s and Cloudflare 503 challenges.

    Known hosts are DOS (``travel.state.gov``, ``ceac.state.gov``), USCIS
    (``uscis.gov`` and its subdomains), and DHS (``dhs.gov``, ``ohss.dhs.gov``).
    404, 500, timeouts, and 403s from any other host (including DOL) are not
    access blocks.
    """
    host = hostname_of(url)
    if status is None or not is_known_upstream_host(host):
        return None
    cf = looks_like_cloudflare(headers, body)
    if status == 403 or (status == 503 and cf):
        return AccessBlock(
            url=url,
            host=host,
            status=status,
            cloudflare=cf,
            source_id=source_id,
        )
    return None


def is_upstream_access_block(message: str, url: Optional[str] = None) -> bool:
    """Classify an already-rendered error string (legacy HTTPError text included)."""
    text = message or ""
    host = hostname_of(url or "") or _host_from_text(text)
    if not is_known_upstream_host(host):
        return False
    if text.startswith("UPSTREAM ACCESS BLOCKED:"):
        return True
    status = _status_from_text(text)
    cf = looks_like_cloudflare(body=text) or "cloudflare" in text.lower()
    if status == 403:
        return True
    if status == 503 and cf:
        return True
    return False


def response_status(resp) -> Optional[int]:
    raw = getattr(resp, "status_code", None)
    if isinstance(raw, bool) or not isinstance(raw, int):
        return None
    return raw


def failure_from_response(
    resp,
    *,
    source_id: str = "",
    fallback_url: str = "",
) -> tuple:
    """Return ``(message, is_access_block)`` for an HTTP error response."""
    status = response_status(resp)
    url = getattr(resp, "url", None) or fallback_url or ""
    if not isinstance(url, str) or not url:
        url = fallback_url or ""
    block = classify_response(
        url=url,
        status=status,
        headers=getattr(resp, "headers", None),
        body=_body_snippet(resp),
        source_id=source_id,
    )
    if block is not None:
        return block.message, True
    reason = getattr(resp, "reason", "") or ""
    if not isinstance(reason, str):
        reason = ""
    code = status if status is not None else "?"
    return f"HTTPError: {code} Client Error: {reason} for url: {url}", False


def _header_map(headers: Optional[Mapping]) -> dict:
    if not headers:
        return {}
    try:
        items = dict(headers).items()
    except Exception:  # noqa: BLE001
        return {}
    out = {}
    for key, value in items:
        try:
            out[str(key).lower()] = str(value).lower()
        except Exception:  # noqa: BLE001
            continue
    return out


def _body_snippet(resp, limit: int = 4096) -> str:
    try:
        content = getattr(resp, "content", b"") or b""
    except Exception:  # noqa: BLE001
        return ""
    if isinstance(content, str):
        return content[:limit]
    if isinstance(content, (bytes, bytearray)):
        return bytes(content[:limit]).decode("utf-8", errors="replace")
    return ""


def _host_from_text(text: str) -> str:
    match = _URL_RE.search(text or "")
    if not match:
        return ""
    return hostname_of(match.group(0))


def _status_from_text(text: str) -> Optional[int]:
    match = _STATUS_RE.search(text or "")
    if not match:
        return None
    raw = match.group(1) or match.group(2)
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None
