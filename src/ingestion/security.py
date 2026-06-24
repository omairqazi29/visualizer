"""Security helpers for data ingestion: safe paths, URL allowlists, size limits."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional, Sequence, Tuple
from urllib.parse import urlparse, unquote

from .registry import DATA_DIR, PROJECT_ROOT

# Max download size (bytes) — prevents disk DoS in CI
MAX_DOWNLOAD_BYTES = 80 * 1024 * 1024  # 80 MB

# Magic bytes / content sniffing
XLSX_MAGIC = b"PK"  # zip-based xlsx
XLS_MAGIC = b"\xd0\xcf\x11\xe0"  # OLE compound
HTML_SNIPPETS = (b"<!doctype html", b"<html", b"<head", b"<body")


def safe_basename(raw_name: str) -> str:
    """Return a filesystem-safe basename; reject path traversal segments.

    Rejects path separators and ``..`` / ``.`` as path *components*, not arbitrary
    ``..`` substrings inside an otherwise normal filename (e.g. ``report..final.xlsx``).
    """
    if not raw_name or not str(raw_name).strip():
        raise ValueError("empty filename")
    raw_s = str(raw_name)
    # Path separators always mean traversal / multi-segment input
    if "/" in raw_s or "\\" in raw_s:
        raise ValueError(f"path traversal rejected: {raw_name!r}")
    name = unquote(raw_s).split("?")[0].strip()
    if not name:
        raise ValueError(f"invalid filename: {raw_name!r}")
    # Only reject .. / . as the entire basename (path component), not substring
    if name in (".", ".."):
        raise ValueError(f"invalid filename: {raw_name!r}")
    if any(ord(c) < 32 for c in name):
        raise ValueError(f"control chars in filename: {raw_name!r}")
    return name


def safe_target_path(target_dir: Path, filename: str) -> Path:
    """Resolve dest under target_dir; raise if escapes target_dir."""
    safe_name = safe_basename(filename)
    target_dir = Path(target_dir).resolve()
    dest = (target_dir / safe_name).resolve()
    try:
        dest.relative_to(target_dir)
    except ValueError as e:
        raise ValueError(f"path escapes target_dir: {dest} not under {target_dir}") from e
    return dest


def is_under_data_dir(path: Path) -> bool:
    """True if path resolves inside project data/ directory."""
    try:
        Path(path).resolve().relative_to(DATA_DIR.resolve())
        return True
    except ValueError:
        return False


def is_allowed_url(url: str, allowed_hosts: Sequence[str]) -> Tuple[bool, str]:
    """Validate scheme + host against allowlist. Returns (ok, reason)."""
    if not url or not isinstance(url, str):
        return False, "empty url"
    try:
        parsed = urlparse(url)
    except Exception as e:  # noqa: BLE001
        return False, f"unparseable url: {e}"
    if parsed.scheme not in ("http", "https"):
        return False, f"scheme not allowed: {parsed.scheme!r}"
    host = (parsed.hostname or "").lower()
    if not host:
        return False, "missing host"
    allowed = [h.lower().lstrip(".") for h in allowed_hosts if h]
    if not allowed:
        return False, "no allowed_hosts configured"
    for ah in allowed:
        if host == ah or host.endswith("." + ah):
            return True, "ok"
    return False, f"host not allowlisted: {host}"


def looks_like_html(first_bytes: bytes) -> bool:
    head = first_bytes[:512].lstrip().lower()
    return any(s in head for s in HTML_SNIPPETS)


def looks_like_spreadsheet(first_bytes: bytes, filename: str = "") -> bool:
    if first_bytes.startswith(XLSX_MAGIC) or first_bytes.startswith(XLS_MAGIC):
        return True
    # CSV/text allowed for some sources
    ext = Path(filename).suffix.lower()
    if ext in (".csv", ".txt", ".ndjson"):
        return True
    if ext == ".zip":
        return first_bytes.startswith(XLSX_MAGIC)  # zip magic is also PK
    if ext in (".html", ".htm"):
        return True  # bulletin pages / metadata only
    return False


def sanitize_pr_filename(path_or_name: str, max_len: int = 120) -> str:
    """Safe display name for PR bodies (basename only, strip markdown meta-chars)."""
    try:
        name = safe_basename(path_or_name)
    except ValueError:
        name = Path(str(path_or_name).replace("\\", "/")).name
        name = re.sub(r"[^\w.\- +()]", "_", name)[:max_len]
    # Strip chars that could break markdown/code fences
    name = re.sub(r"[`*\[\]<>|]", "", name)
    if len(name) > max_len:
        name = name[: max_len - 3] + "..."
    return name or "unknown"


def detect_default_branch(project_root: Optional[Path] = None) -> str:
    """Best-effort default branch detection; prefers master for this repo."""
    import subprocess

    root = str(project_root or PROJECT_ROOT)
    # gh repo view
    try:
        r = subprocess.run(
            ["gh", "repo", "view", "--json", "defaultBranchRef", "-q", ".defaultBranchRef.name"],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=10,
        )
        if r.returncode == 0 and (r.stdout or "").strip():
            return r.stdout.strip()
    except Exception:  # noqa: BLE001
        pass
    # git symbolic-ref
    try:
        r = subprocess.run(
            ["git", "symbolic-ref", "refs/remotes/origin/HEAD"],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if r.returncode == 0 and r.stdout:
            ref = r.stdout.strip()
            if "/" in ref:
                return ref.rsplit("/", 1)[-1]
    except Exception:  # noqa: BLE001
        pass
    return "master"  # this repo's default
