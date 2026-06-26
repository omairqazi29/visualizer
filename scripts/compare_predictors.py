#!/usr/bin/env python3
"""Compare VBPredictor vs DemandModeler for a priority date.

Runs locally via shared build_predictor_compare (no server required), or
optionally hits a running API via --base-url / API_BASE_URL.

Usage:
  python scripts/compare_predictors.py --priority-date 2022-10-01
  python scripts/compare_predictors.py --priority-date 2023-04-01 --restrictions
  python scripts/compare_predictors.py --priority-date 2022-10-01 --base-url http://localhost:8000
  API_BASE_URL=http://api:8000 python scripts/compare_predictors.py --priority-date 2022-10-01
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

_ALLOWED_SCHEMES = frozenset({"http", "https"})


def _validate_base_url(base_url: str) -> str:
    parsed = urlparse(base_url)
    if parsed.scheme not in _ALLOWED_SCHEMES:
        raise ValueError(
            f"--base-url scheme must be http or https (got {parsed.scheme!r})"
        )
    if not parsed.netloc:
        raise ValueError("--base-url must include a host")
    return base_url.rstrip("/")


def compare_api(base_url: str, priority_date: str, category: str, restrictions: bool,
                retries: int = 8, delay: float = 1.0) -> dict:
    params = urllib.parse.urlencode({
        "priority_date": priority_date,
        "category": category,
        "apply_real_restrictions": str(restrictions).lower(),
    })
    url = f"{_validate_base_url(base_url)}/api/predictor-compare?{params}"
    last_err: Exception | None = None
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(url, timeout=60) as resp:
                if resp.status >= 400:
                    body = resp.read().decode(errors="replace")
                    raise RuntimeError(f"HTTP {resp.status}: {body[:200]}")
                return json.loads(resp.read().decode())
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, RuntimeError) as exc:
            last_err = exc
            if attempt + 1 < retries:
                time.sleep(delay)
                continue
            raise
    raise RuntimeError(str(last_err))


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare VB vs demand predictors")
    parser.add_argument("--priority-date", required=True, help="YYYY-MM-DD")
    parser.add_argument("--category", default="EB-1")
    parser.add_argument("--restrictions", action="store_true")
    parser.add_argument(
        "--base-url",
        default=os.environ.get("API_BASE_URL"),
        help="Call /api/predictor-compare (default: API_BASE_URL env, else in-process)",
    )
    args = parser.parse_args()

    try:
        if args.base_url:
            result = compare_api(
                args.base_url, args.priority_date, args.category, args.restrictions
            )
        else:
            from src.engine.predictor_compare import build_predictor_compare
            result = build_predictor_compare(
                priority_date=args.priority_date,
                category=args.category,
                apply_real_restrictions=args.restrictions,
            )
    except ValueError as exc:
        print(f"usage error: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(result, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
