"""Automated data source scanning, fetching, and PR helpers for The Spillover Engine."""

from .registry import SOURCE_REGISTRY, get_source, list_sources
from .scanner import scan_source, scan_sources
from .fetcher import fetch_candidate, fetch_candidates
from .validator import validate_downloaded_files
from .pr_helper import create_data_pr, propose_branch_name
from .security import safe_basename, safe_target_path, is_allowed_url

__all__ = [
    "SOURCE_REGISTRY",
    "get_source",
    "list_sources",
    "scan_source",
    "scan_sources",
    "fetch_candidate",
    "fetch_candidates",
    "validate_downloaded_files",
    "create_data_pr",
    "propose_branch_name",
    "safe_basename",
    "safe_target_path",
    "is_allowed_url",
]
