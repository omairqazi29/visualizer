"""Create git branch + commit + GitHub PR for newly ingested data files."""

from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import List, Optional, Sequence

from .registry import PROJECT_ROOT, get_source
from .scanner import RemoteCandidate, ScanResult


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


def propose_branch_name(source_ids: Sequence[str], when: Optional[date] = None) -> str:
    d = (when or date.today()).isoformat()
    if not source_ids:
        src = "all"
    elif len(source_ids) == 1:
        src = source_ids[0]
    else:
        src = "multi"
    # sanitize
    src = src.replace("/", "-").replace(" ", "-")
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
            lines.append(f"- **{sid}** ({src.agency}): {src.description}")
            lines.append(f"  - Engine: {src.engine_notes}")
        except KeyError:
            lines.append(f"- **{sid}**")

    lines.extend(["", "### New / updated files"])
    if fetched_files:
        for f in fetched_files:
            lines.append(f"- `{f}`")
    else:
        lines.append("_No binary data files downloaded (may be bulletin metadata only)._")

    lines.extend(["", "### Scan highlights"])
    for sr in scan_results:
        lines.append(
            f"- `{sr.source_id}`: {len(sr.new_candidates)} new, "
            f"{len(sr.existing_candidates)} already present"
        )
        for c in sr.new_candidates[:8]:
            lines.append(f"  - {c.filename}")

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
    base_branch: str = "main",
) -> PRResult:
    """Stage files, commit on a chore/data-* branch, and open a PR via gh.

    In GitHub Actions, GITHUB_TOKEN / GH_TOKEN must have contents:write + pull-requests:write.
    """
    scan_results = scan_results or []
    files = [f for f in files if f]
    branch = branch_name or propose_branch_name(source_ids)

    if not files:
        # Allow bulletin-only updates via .seen_bulletins.txt
        pass

    title_src = source_ids[0] if len(source_ids) == 1 else "data sources"
    title = commit_message or f"chore(data): add latest {title_src} files"
    if not title.startswith("chore"):
        title = f"chore(data): {title}"

    if dry_run:
        body = build_pr_body(scan_results, files, source_ids=source_ids)
        return PRResult(
            success=True,
            branch=branch,
            message=f"dry-run: would create branch {branch}, commit {len(files)} file(s), PR title: {title}",
            dry_run=True,
            committed_files=list(files),
        )

    if not _git_available():
        return PRResult(success=False, message="git not available")

    # Create / checkout branch
    cur = _run(["git", "rev-parse", "--abbrev-ref", "HEAD"])
    current_branch = (cur.stdout or "").strip()

    # If detached HEAD (worktree), create branch from HEAD
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
            return PRResult(
                success=False,
                branch=branch,
                message=f"git add failed: {add.stderr or add.stdout}",
            )

    # Check if anything staged
    staged = _run(["git", "diff", "--cached", "--name-only"])
    staged_files = [ln for ln in (staged.stdout or "").splitlines() if ln.strip()]
    if not staged_files:
        return PRResult(
            success=False,
            branch=branch,
            message="nothing staged to commit (no new files or already committed)",
            committed_files=[],
        )

    body = build_pr_body(scan_results, staged_files, source_ids=source_ids)
    commit = _run(["git", "commit", "-m", title, "-m", body[:2000]])
    if commit.returncode != 0:
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
        # Maybe PR already exists
        return PRResult(
            success=False,
            branch=branch,
            message=f"gh pr create failed: {pr.stderr or pr.stdout}",
            committed_files=staged_files,
        )

    pr_url = (pr.stdout or "").strip().splitlines()[-1] if pr.stdout else ""
    return PRResult(
        success=True,
        branch=branch,
        pr_url=pr_url,
        message="PR created",
        committed_files=staged_files,
    )


def paths_from_fetch_results(fetch_results) -> List[str]:
    """Collect relative paths suitable for git add."""
    out: List[str] = []
    for fr in fetch_results:
        if not fr.success or fr.skipped or fr.dry_run:
            continue
        if fr.path is None:
            continue
        p = Path(fr.path)
        try:
            rel = p.resolve().relative_to(PROJECT_ROOT.resolve())
            out.append(str(rel))
        except ValueError:
            out.append(str(p))
    return out
