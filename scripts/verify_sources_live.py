#!/usr/bin/env python3
"""Live smoke verification of public data source pages (integration).

Run explicitly:
  python scripts/verify_sources_live.py
  python -m pytest tests/test_ingestion.py -m integration -v
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.ingestion.registry import USER_AGENT, get_source
from src.ingestion.scanner import extract_links, scan_source

try:
    import requests
except ImportError:
    print("requests required", file=sys.stderr)
    sys.exit(1)


def check_dos_fsc() -> bool:
    src = get_source("dos_iv_fsc")
    r = requests.get(src.scan_url, headers={"User-Agent": USER_AGENT}, timeout=45)
    r.raise_for_status()
    links = extract_links(r.text, src.scan_url)
    fsc = [
        u
        for u, t in links
        if u.lower().endswith(".xlsx")
        and ("FSC" in u or "Place%20of%20Birth" in u or "Place of Birth" in t)
    ]
    print(f"DOS: {len(fsc)} FSC xlsx links")
    result = scan_source(src, delay=0.2)
    print(f"DOS scan: {len(result.candidates)} candidates, page_fetched={result.page_fetched}")
    return len(fsc) >= 10 and result.page_fetched


def check_uscis() -> bool:
    src = get_source("uscis_i140")
    r = requests.get(src.scan_url, headers={"User-Agent": USER_AGENT}, timeout=45)
    r.raise_for_status()
    links = extract_links(r.text, src.scan_url)
    xlsx = [u for u, _ in links if u.lower().endswith((".xlsx", ".xls"))]
    inv = [u for u in xlsx if "inventory" in u.lower()]
    print(f"USCIS: {len(xlsx)} xlsx links, {len(inv)} inventory (often 0 on landing page)")
    result = scan_source(src, delay=0.2)
    print(f"USCIS i140 scan: {len(result.candidates)} candidates")
    return result.page_fetched and len(xlsx) >= 1


def main() -> int:
    print("=== Live source verification ===")
    ok_dos = check_dos_fsc()
    ok_uscis = check_uscis()
    print(f"dos_ok={ok_dos} uscis_ok={ok_uscis}")
    return 0 if (ok_dos and ok_uscis) else 1


if __name__ == "__main__":
    raise SystemExit(main())
