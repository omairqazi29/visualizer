#!/usr/bin/env python3
"""CLI entrypoint for automated data source scan / fetch / validate / PR.

Usage examples:
  python -m src.scripts.scan_and_pr --scan --dry-run
  python -m src.scripts.scan_and_pr --scan --fetch --source dos_iv
  python -m src.scripts.scan_and_pr --scan --fetch --validate --pr --source uscis
  python -m src.scripts.scan_and_pr --list-sources

Environment:
  GITHUB_TOKEN / GH_TOKEN — required for --pr in CI (gh auth)
  GITHUB_RUN_ID — included in branch names when set (CI)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Project root on path
_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from src.ingestion.registry import (  # noqa: E402
    SOURCE_GROUPS,
    SOURCE_REGISTRY,
    REQUEST_DELAY_SEC,
    list_sources,
    resolve_source_ids,
)
from src.ingestion.scanner import scan_sources, summarize_scan  # noqa: E402
from src.ingestion.fetcher import (  # noqa: E402
    any_fetch_failed,
    fetch_from_scan_results,
    summarize_fetch,
)
from src.ingestion.validator import (  # noqa: E402
    validate_downloaded_files,
    summarize_validation,
)
from src.ingestion.pr_helper import (  # noqa: E402
    create_data_pr,
    paths_from_fetch_results,
    propose_branch_name,
)
from src.ingestion.security import detect_default_branch  # noqa: E402


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m src.scripts.scan_and_pr",
        description="Scan public DOS/USCIS data pages, download new files, validate, open PR.",
    )
    p.add_argument(
        "--source",
        default="all",
        help=(
            "Source id or group: all | all_including_vb | dos_iv | visa_bulletin | uscis | "
            "uscis_inventory | uscis_i485_perf | uscis_i140 | dhs | dol | supply | "
            "<source_id> | comma-list. Note: `all` excludes visa_bulletin (use dedicated workflow)."
        ),
    )
    p.add_argument("--scan", action="store_true", help="Scan configured source pages for links")
    p.add_argument("--fetch", action="store_true", help="Download new files (after --scan)")
    p.add_argument("--validate", action="store_true", help="Run parser/validation checks")
    p.add_argument("--pr", action="store_true", help="Commit + open GitHub PR via gh (needs auth)")
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Do not write files / commit / open PR (scan still hits the network)",
    )
    p.add_argument(
        "--list-sources",
        action="store_true",
        help="Print registered sources and exit",
    )
    p.add_argument(
        "--delay",
        type=float,
        default=REQUEST_DELAY_SEC,
        help=f"Seconds between HTTP requests (default {REQUEST_DELAY_SEC})",
    )
    p.add_argument(
        "--json",
        action="store_true",
        dest="as_json",
        help="Emit machine-readable JSON summary on stdout (after human-readable logs)",
    )
    p.add_argument(
        "--include-baseline-validate",
        action="store_true",
        help="With --validate, also check currently discovered inventory/pipeline/DOS",
    )
    p.add_argument(
        "--base-branch",
        default="auto",
        help="Base branch for PR (default: auto — detect via gh/git, else master)",
    )
    p.add_argument(
        "--branch-name",
        default=None,
        help="Override chore/data-* branch name",
    )
    p.add_argument(
        "--allow-scan-errors",
        action="store_true",
        help="Exit 0 even when some source scans fail (default: exit 1 on scan failure)",
    )
    return p


def _print_sources() -> None:
    print("Registered data sources:\n")
    for sid, src in sorted(SOURCE_REGISTRY.items()):
        flag = "ON " if src.enabled else "off"
        print(f"  [{flag}] {sid:22s} ({src.agency:5s}) {src.description[:70]}")
        print(f"         scan: {src.scan_url}")
        print(f"         dest: {src.target_dir}")
        print(f"         engine: {src.engine_notes[:90]}")
        print()
    print("Groups:")
    for g, ids in sorted(SOURCE_GROUPS.items()):
        print(f"  {g:20s} -> {', '.join(ids)}")


def main(argv: list | None = None) -> int:
    args = _build_parser().parse_args(argv)

    if args.list_sources:
        _print_sources()
        return 0

    # Default action: scan if nothing specified
    if not any([args.scan, args.fetch, args.validate, args.pr]):
        args.scan = True

    try:
        source_ids = resolve_source_ids(args.source)
    except KeyError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 2

    payload: dict = {
        "source_ids": source_ids,
        "dry_run": args.dry_run,
        "scan": None,
        "fetch": None,
        "validate": None,
        "pr": None,
        "exit_hints": [],
    }

    scan_results = []
    fetch_results = []
    exit_code = 0

    if args.scan or args.fetch or args.pr:
        print(f"Scanning sources: {', '.join(source_ids)} (dry_run={args.dry_run})")
        scan_results = scan_sources(
            source_ids,
            delay=0.05 if args.dry_run else args.delay,
            dry_run=args.dry_run,
        )
        print(summarize_scan(scan_results))
        payload["scan"] = [r.to_dict() for r in scan_results]

        scan_failed = any(not r.page_fetched for r in scan_results)
        if scan_failed and not args.allow_scan_errors:
            print("ERROR: one or more source scans failed", file=sys.stderr)
            exit_code = 1
            payload["exit_hints"].append("scan_failed")
            # Still allow fetch/validate/pr on partial success only if not failing closed early
            # For fail-closed: stop before PR when scan failed
            if args.pr and not args.dry_run:
                if args.as_json:
                    print(json.dumps(payload, indent=2, default=str))
                return 1

    if args.fetch:
        print("\nFetching new candidates...")
        fetch_results = fetch_from_scan_results(
            scan_results,
            delay=0.05 if args.dry_run else args.delay,
            dry_run=args.dry_run,
            new_only=True,
        )
        print(summarize_fetch(fetch_results))
        payload["fetch"] = [r.to_dict() for r in fetch_results]

        if any_fetch_failed(fetch_results) and not args.dry_run:
            ok_n = sum(1 for r in fetch_results if r.success and not r.skipped and not r.dry_run)
            fail_n = sum(1 for r in fetch_results if not r.success and not r.skipped)
            # Partial success: still allow PR for successful downloads; only hard-fail if nothing worked
            if ok_n == 0 and fail_n > 0:
                print("ERROR: all fetches failed — refusing PR", file=sys.stderr)
                exit_code = 1
                payload["exit_hints"].append("fetch_all_failed")
                if args.pr:
                    if args.as_json:
                        print(json.dumps(payload, indent=2, default=str))
                    return 1
            else:
                print(
                    f"WARNING: {fail_n} fetch(es) failed; continuing with {ok_n} successful download(s)",
                    file=sys.stderr,
                )
                payload["exit_hints"].append("fetch_partial_failed")
                exit_code = 1  # non-zero overall so CI shows warning; PR may still proceed below

    if args.validate:
        print("\nValidating...")
        paths = []
        for fr in fetch_results:
            if fr.path and fr.success and not fr.dry_run and not fr.skipped:
                paths.append(fr.path)
        cands = []
        for sr in scan_results:
            cands.extend(sr.new_candidates)

        strict = bool(args.pr) and not args.dry_run
        report = validate_downloaded_files(
            paths=paths or None,
            candidates=cands if not paths else None,
            include_baseline=args.include_baseline_validate or (not paths and not cands),
            strict_unknown=strict,
            require_under_data=strict,
        )
        if not report.items:
            report = validate_downloaded_files(
                include_baseline=True,
                strict_unknown=False,
                require_under_data=False,
            )
        print(summarize_validation(report))
        payload["validate"] = report.to_dict()
        if not report.ok and not args.dry_run:
            print("ERROR: validation failed — refusing PR", file=sys.stderr)
            exit_code = 1
            payload["exit_hints"].append("validate_failed")
            if args.pr:
                if args.as_json:
                    print(json.dumps(payload, indent=2, default=str))
                return 1

    if args.pr:
        # Fail closed only when every attempted fetch failed (partial success is OK)
        if args.fetch and fetch_results and not args.dry_run:
            ok_n = sum(1 for r in fetch_results if r.success and not r.skipped and not r.dry_run)
            fail_n = sum(1 for r in fetch_results if not r.success and not r.skipped)
            if ok_n == 0 and fail_n > 0:
                if args.as_json:
                    print(json.dumps(payload, indent=2, default=str))
                return 1

        files = paths_from_fetch_results(fetch_results)
        branch = args.branch_name or propose_branch_name(source_ids)
        base = args.base_branch
        if base in (None, "", "auto"):
            base = detect_default_branch(_ROOT)
        print(f"\nPR step (branch={branch}, base={base}, dry_run={args.dry_run})...")
        pr_result = create_data_pr(
            files=files,
            source_ids=source_ids,
            scan_results=scan_results,
            branch_name=branch,
            dry_run=args.dry_run,
            base_branch=base,
        )
        print(f"  success={pr_result.success}")
        print(f"  branch={pr_result.branch}")
        if pr_result.pr_url:
            print(f"  pr_url={pr_result.pr_url}")
        print(f"  message={pr_result.message}")
        if pr_result.committed_files:
            print(f"  files={pr_result.committed_files}")
        payload["pr"] = pr_result.to_dict()
        if not pr_result.success and not args.dry_run:
            if "nothing staged" in (pr_result.message or ""):
                print("No new data to PR (this is OK if all sources are up to date).")
            else:
                exit_code = 1
                if args.as_json:
                    print(json.dumps(payload, indent=2, default=str))
                return 1

    if args.as_json:
        print(json.dumps(payload, indent=2, default=str))

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
