"""Create git branch + commit + GitHub PR for newly ingested data files."""

from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import List, Optional, Sequence

from .registry import DATA_DIR, PROJECT_ROOT, get_source
from .scanner import ScanResult
from .security import detect_default_branch, is_under_data_dir, sanitize_pr_filename


@dataclass
class PRResult:
    success: bool
    branch: str = ""
    pr_url: str = ""
    message: str = ""
    dry_run: bool = False
    committed_files: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "branch": self.branch,
            "pr_url": self.pr_url,
            "message": self.message,
            "dry_run": self.dry_run,
            "committed_files": self.committed_files,
        }


def propose_branch_name(
    source_ids: Sequence[str],
    when: Optional[date] = None,
    run_id: Optional[str] = None,
) -> str:
    d = (when or date.today()).isoformat()
    if not source_ids:
        src = "all"
    elif len(source_ids) == 1:
        src = source_ids[0]
    else:
        src = "multi"
    # sanitize for git branch safety
    src = re.sub(r"[^a-zA-Z0-9._-]", "-", src)
    rid = run_id or os.environ.get("GITHUB_RUN_ID") or os.environ.get("CI_RUN_ID") or ""
    rid = re.sub(r"[^a-zA-Z0-9._-]", "", str(rid))[:12]
    if rid:
        return f"chore/data-{src}-{d}-{rid}"
    return f"chore/data-{src}-{d}"


def _run(
    cmd: List[str],
    *,
    cwd: Optional[Path] = None,
    check: bool = False,
) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd,
        cwd=str(cwd or PROJECT_ROOT),
        capture_output=True,
        text=True,
        check=check,
    )


def _gh_available() -> bool:
    r = _run(["gh", "--version"])
    return r.returncode == 0


def _git_available() -> bool:
    r = _run(["git", "--version"])
    return r.returncode == 0


def filter_paths_for_pr(files: Sequence[str]) -> List[str]:
    """Only allow paths under data/ to be staged (security)."""
    out: List[str] = []
    for f in files:
        if not f:
            continue
        p = Path(f)
        if not p.is_absolute():
            p = PROJECT_ROOT / p
        try:
            if is_under_data_dir(p):
                try:
                    rel = p.resolve().relative_to(PROJECT_ROOT.resolve())
                    out.append(str(rel))
                except ValueError:
                    out.append(f)
        except Exception:  # noqa: BLE001
            continue
    return out


def build_pr_body(
    scan_results: Sequence[ScanResult],
    fetched_files: Sequence[str],
    *,
    source_ids: Sequence[str],
) -> str:
    lines = [
        "## Automated data ingestion",
        "",
        "This PR was opened by the Spillover Engine data-scan pipeline "
        "(`src/ingestion/` + `.github/workflows/data-scan.yml`).",
        "",
        "### Sources scanned",
    ]
    for sid in source_ids:
        try:
            src = get_source(sid)
            safe_desc = re.sub(r"[`*\[\]<>|]", "", src.description)[:200]
            safe_engine = re.sub(r"[`*\[\]<>|]", "", src.engine_notes)[:200]
            lines.append(f"- **{sid}** ({src.agency}): {safe_desc}")
            lines.append(f"  - Engine: {safe_engine}")
        except KeyError:
            lines.append(f"- **{sid}**")

    lines.extend(["", "### New / updated files"])
    if fetched_files:
        for f in fetched_files:
            lines.append(f"- `{sanitize_pr_filename(f)}`")
    else:
        lines.append("_No binary data files downloaded (may be bulletin metadata only)._")

    lines.extend(["", "### Scan highlights"])
    for sr in scan_results:
        lines.append(
            f"- `{sr.source_id}`: {len(sr.new_candidates)} new, "
            f"{len(sr.existing_candidates)} already present"
        )
        for c in sr.new_candidates[:8]:
            lines.append(f"  - {sanitize_pr_filename(c.filename)}")

    lines.extend(
        [
            "",
            "### Post-merge checklist",
            "- [ ] Confirm parsers accept the new files (`python -m src.scripts.scan_and_pr --validate`)",
            "- [ ] Run `python3 -m pytest tests/ -v`",
            "- [ ] If supply/demand inputs changed, update changelog in `docs/POLICY_VERIFICATION.md`",
            "- [ ] For Visa Bulletin: ensure `data/visa_bulletin/*_history.csv` rows added if needed",
            "",
            "### Drop-in behavior",
            "Parsers auto-discover newest files via `src/data_discovery.py` — no code changes required "
            "for normal DOS/USCIS Excel drops.",
        ]
    )
    return "\n".join(lines)


def create_data_pr(
    *,
    files: Sequence[str],
    source_ids: Sequence[str],
    scan_results: Optional[Sequence[ScanResult]] = None,
    branch_name: Optional[str] = None,
    commit_message: Optional[str] = None,
    dry_run: bool = False,
    base_branch: Optional[str] = None,
    restore_branch: bool = True,
) -> PRResult:
    """Stage files, commit on a chore/data-* branch, and open a PR via gh.

    In GitHub Actions, GITHUB_TOKEN / GH_TOKEN must have contents:write + pull-requests:write.
    Restores prior branch/HEAD in finally when restore_branch=True (default).
    """
    scan_results = scan_results or []
    files = filter_paths_for_pr([f for f in files if f])
    branch = branch_name or propose_branch_name(source_ids)
    branch = re.sub(r"[^a-zA-Z0-9._/-]", "-", branch)

    if base_branch is None or base_branch in ("", "auto"):
        base_branch = detect_default_branch(PROJECT_ROOT)

    title_src = source_ids[0] if len(source_ids) == 1 else "data sources"
    title = commit_message or f"chore(data): add latest {title_src} files"
    if not title.startswith("chore"):
        title = f"chore(data): {title}"

    if dry_run:
        body = build_pr_body(scan_results, files, source_ids=source_ids)
        return PRResult(
            success=True,
            branch=branch,
            message=(
                f"dry-run: would create branch {branch}, commit {len(files)} file(s), "
                f"PR title: {title}, base: {base_branch}"
            ),
            dry_run=True,
            committed_files=list(files),
        )

    if not _git_available():
        return PRResult(success=False, message="git not available")

    # Capture prior HEAD for restore
    cur = _run(["git", "rev-parse", "--abbrev-ref", "HEAD"])
    current_branch = (cur.stdout or "").strip()
    sha_r = _run(["git", "rev-parse", "HEAD"])
    prior_sha = (sha_r.stdout or "").strip()
    was_detached = current_branch in ("HEAD", "")
    op_succeeded = False

    def _clear_index_if_dirty() -> None:
        """Unstage everything so a failed PR attempt does not leave a dirty index."""
        _run(["git", "reset", "HEAD"])

    try:
        br = _run(["git", "checkout", "-B", branch])
        if br.returncode != 0:
            return PRResult(
                success=False,
                branch=branch,
                message=f"git checkout failed: {br.stderr or br.stdout}",
            )

        if files:
            add = _run(["git", "add", "--"] + list(files))
            if add.returncode != 0:
                _clear_index_if_dirty()
                return PRResult(
                    success=False,
                    branch=branch,
                    message=f"git add failed: {add.stderr or add.stdout}",
                )

        staged = _run(["git", "diff", "--cached", "--name-only"])
        staged_files = [ln for ln in (staged.stdout or "").splitlines() if ln.strip()]
        # Double-check staged paths under data/
        staged_files = filter_paths_for_pr(staged_files)
        if not staged_files:
            _clear_index_if_dirty()
            return PRResult(
                success=False,
                branch=branch,
                message="nothing staged to commit (no new files or already committed)",
                committed_files=[],
            )

        body = build_pr_body(scan_results, staged_files, source_ids=source_ids)
        commit = _run(["git", "commit", "-m", title, "-m", body[:2000]])
        if commit.returncode != 0:
            _clear_index_if_dirty()
            return PRResult(
                success=False,
                branch=branch,
                message=f"git commit failed: {commit.stderr or commit.stdout}",
            )

        push = _run(["git", "push", "-u", "origin", branch])
        if push.returncode != 0:
            return PRResult(
                success=False,
                branch=branch,
                message=f"git push failed: {push.stderr or push.stdout}",
                committed_files=staged_files,
            )

        if not _gh_available():
            op_succeeded = True
            return PRResult(
                success=True,
                branch=branch,
                message="committed+pushed but gh CLI not available — open PR manually",
                committed_files=staged_files,
            )

        pr = _run(
            [
                "gh",
                "pr",
                "create",
                "--base",
                base_branch,
                "--head",
                branch,
                "--title",
                title,
                "--body",
                body,
            ]
        )
        if pr.returncode != 0:
            return PRResult(
                success=False,
                branch=branch,
                message=f"gh pr create failed: {pr.stderr or pr.stdout}",
                committed_files=staged_files,
            )

        pr_url = (pr.stdout or "").strip().splitlines()[-1] if pr.stdout else ""
        op_succeeded = True
        return PRResult(
            success=True,
            branch=branch,
            pr_url=pr_url,
            message="PR created",
            committed_files=staged_files,
        )
    finally:
        if restore_branch:
            # On failure before commit, ensure index is clean before leaving the branch
            if not op_succeeded:
                _clear_index_if_dirty()
            if was_detached and prior_sha:
                _run(["git", "checkout", prior_sha])
            elif current_branch and current_branch != branch:
                _run(["git", "checkout", current_branch])


def paths_from_fetch_results(fetch_results) -> List[str]:
    """Collect relative paths under data/ suitable for git add."""
    out: List[str] = []
    for fr in fetch_results:
        if not fr.success or fr.skipped or fr.dry_run:
            continue
        if fr.path is None:
            continue
        p = Path(fr.path)
        if not is_under_data_dir(p):
            continue
        try:
            rel = p.resolve().relative_to(PROJECT_ROOT.resolve())
            out.append(str(rel))
        except ValueError:
            continue
    return out
