"""Mock government data publisher for data-scan e2e tests.

Serves HTML index pages + minimal xlsx/csv fixtures that match real DOS/USCIS
filename patterns. No network dependency on travel.state.gov / uscis.gov.

Endpoints:
  GET  /health
  GET  /dos/monthly          — DOS IV FSC index HTML
  GET  /uscis/data           — USCIS reports index HTML
  GET  /files/<path>         — downloadable fixtures
  POST /publish/new          — add a new DOS month dynamically (JSON body optional)
  GET  /status               — list currently published files

Run locally:
  python tests/e2e/mock_data_server/server.py
  # or: uvicorn tests.e2e.mock_data_server.server:app --host 0.0.0.0 --port 8765
"""

from __future__ import annotations

import io
import os
import threading
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import quote

from fastapi import FastAPI, HTTPException, Response
from fastapi.responses import HTMLResponse, JSONResponse
from openpyxl import Workbook

PORT = int(os.environ.get("MOCK_DATA_PORT", "8765"))
HOST = os.environ.get("MOCK_DATA_HOST", "0.0.0.0")

app = FastAPI(title="Mock Government Data Publisher", version="1.0.0")

# Thread-safe published file registry: path_key -> (filename, content_bytes, content_type)
_lock = threading.Lock()
_files: Dict[str, tuple] = {}
_publish_counter = 0

# Initial seed files (always present at startup)
_SEED_DOS = [
    "OCTOBER 2025 - IV Issuances by FSC or Place of Birth and Visa Class.xlsx",
    "NOVEMBER 2025 - IV Issuances by FSC or Place of Birth and Visa Class.xlsx",
]
_SEED_USCIS = [
    ("inventory", "eb_inventory_november_2025.xlsx"),
    ("i485", "i485_performance_fy2025_q4.xlsx"),
    ("i140", "eb_i140_i360_i526_performance_data_fy2025_q4_v1.xlsx"),
    ("i140_rec", "i140_rec_by_class_country_fy2025_q4_v1.xlsx"),
]

_MONTHS = [
    "JANUARY", "FEBRUARY", "MARCH", "APRIL", "MAY", "JUNE",
    "JULY", "AUGUST", "SEPTEMBER", "OCTOBER", "NOVEMBER", "DECEMBER",
]


def _minimal_xlsx(sheet_title: str = "Sheet1", rows: Optional[List[list]] = None) -> bytes:
    """Build a tiny valid xlsx in memory (PK zip magic for fetcher sniffing)."""
    wb = Workbook()
    ws = wb.active
    ws.title = sheet_title[:31]
    if rows:
        for r in rows:
            ws.append(r)
    else:
        ws.append(["FSC", "Visa Class", "Issuances"])
        ws.append(["INDIA", "E1", 100])
        ws.append(["INDIA", "E2", 50])
        ws.append(["CHINA-MAINLAND BORN", "E1", 30])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _register_file(path_key: str, filename: str, content: bytes, content_type: str = None) -> None:
    ct = content_type or (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        if filename.lower().endswith((".xlsx", ".xls"))
        else "application/octet-stream"
    )
    with _lock:
        _files[path_key] = (filename, content, ct)


def _seed_files() -> None:
    """Populate initial fixture set."""
    for name in _SEED_DOS:
        key = f"dos/{name}"
        _register_file(key, name, _minimal_xlsx("DOS_IV", [
            ["FSC or Place of Birth", "Visa Class", "Issuances"],
            ["INDIA", "E1", 42],
            ["MEXICO", "F1", 10],
        ]))
    for category, name in _SEED_USCIS:
        key = f"uscis/{name}"
        _register_file(key, name, _minimal_xlsx("USCIS", [
            ["Category", "Country", "Count"],
            ["EB-1", "India", 1000],
            ["EB-2", "India", 2000],
        ]))


_seed_files()


def _file_url(path_key: str) -> str:
    return f"/files/{quote(path_key, safe='/')}"


def _dos_html() -> str:
    with _lock:
        dos_items = [(k, v[0]) for k, v in _files.items() if k.startswith("dos/")]
    links = []
    for key, fname in sorted(dos_items, key=lambda x: x[1]):
        href = _file_url(key)
        links.append(
            f'<li><a href="{href}">IV Issuances by FSC or Place of Birth — {fname}</a></li>'
        )
    body = "\n".join(links) or "<li>(no files)</li>"
    return f"""<!DOCTYPE html>
<html><head><title>Mock DOS Monthly IV Issuances</title></head>
<body>
<h1>Immigrant Visa Statistics — Monthly IV Issuances (MOCK)</h1>
<p>Mock index for data-scan e2e. Filenames match real DOS FSC pattern.</p>
<ul>
{body}
</ul>
</body></html>"""


def _uscis_html() -> str:
    with _lock:
        uscis_items = [(k, v[0]) for k, v in _files.items() if k.startswith("uscis/")]
    links = []
    for key, fname in sorted(uscis_items, key=lambda x: x[1]):
        href = _file_url(key)
        links.append(f'<li><a href="{href}">{fname}</a></li>')
    body = "\n".join(links) or "<li>(no files)</li>"
    return f"""<!DOCTYPE html>
<html><head><title>Mock USCIS Immigration Data</title></head>
<body>
<h1>Immigration and Citizenship Data (MOCK)</h1>
<p>Mock USCIS reports landing page for data-scan e2e.</p>
<ul>
{body}
</ul>
</body></html>"""


@app.get("/health")
def health():
    with _lock:
        n = len(_files)
    return {"status": "ok", "files_published": n, "service": "mock-data-publisher"}


@app.get("/status")
def status():
    with _lock:
        files = [
            {"path_key": k, "filename": v[0], "size": len(v[1])}
            for k, v in sorted(_files.items())
        ]
    return {"files": files, "count": len(files)}


@app.get("/dos/monthly", response_class=HTMLResponse)
def dos_monthly():
    return _dos_html()


@app.get("/uscis/data", response_class=HTMLResponse)
def uscis_data():
    return _uscis_html()


@app.get("/files/{path_key:path}")
def serve_file(path_key: str):
    with _lock:
        entry = _files.get(path_key)
    if not entry:
        raise HTTPException(status_code=404, detail=f"file not found: {path_key}")
    filename, content, ct = entry
    return Response(
        content=content,
        media_type=ct,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Content-Length": str(len(content)),
        },
    )


@app.post("/publish/new")
def publish_new(body: Optional[dict] = None):
    """Add a new DOS FSC xlsx (next synthetic month) so a second scan sees status=new.

    Optional JSON body:
      {"kind": "dos"} | {"kind": "uscis_inventory", "month": "december_2025"}
      | {"filename": "...", "kind": "dos"}
    Returns the published filename + url.
    """
    global _publish_counter
    body = body or {}
    kind = (body.get("kind") or "dos").lower()

    with _lock:
        _publish_counter += 1
        counter = _publish_counter

    if kind in ("dos", "dos_iv", "dos_iv_fsc"):
        # Pick a month/year not already seeded (use far-future synthetic months)
        # Seed has OCT/NOV 2025; publish DECEMBER 2025, then JANUARY 2026, etc.
        base_names = set(_SEED_DOS)
        with _lock:
            existing = {v[0] for k, v in _files.items() if k.startswith("dos/")}
        # Walk synthetic sequence
        candidates = [
            "DECEMBER 2025 - IV Issuances by FSC or Place of Birth and Visa Class.xlsx",
            "JANUARY 2026 - IV Issuances by FSC or Place of Birth and Visa Class.xlsx",
            "FEBRUARY 2026 - IV Issuances by FSC or Place of Birth and Visa Class.xlsx",
            "MARCH 2026 - IV Issuances by FSC or Place of Birth and Visa Class.xlsx",
            "APRIL 2026 - IV Issuances by FSC or Place of Birth and Visa Class.xlsx",
            "MAY 2026 - IV Issuances by FSC or Place of Birth and Visa Class.xlsx",
        ]
        explicit = body.get("filename")
        if explicit:
            fname = explicit
        else:
            fname = None
            for c in candidates:
                if c not in existing and c not in base_names:
                    fname = c
                    break
            if not fname:
                fname = (
                    f"JUNE 20{26 + counter} - IV Issuances by FSC or Place of Birth "
                    f"and Visa Class.xlsx"
                )
        key = f"dos/{fname}"
        content = _minimal_xlsx("DOS_IV_NEW", [
            ["FSC or Place of Birth", "Visa Class", "Issuances"],
            ["INDIA", "E1", 99 + counter],
            ["BRAZIL", "F1", counter],
        ])
        _register_file(key, fname, content)
        return JSONResponse({
            "ok": True,
            "kind": "dos",
            "filename": fname,
            "path_key": key,
            "url": _file_url(key),
            "scan_page": "/dos/monthly",
            "publish_counter": counter,
        })

    if kind in ("uscis", "uscis_inventory", "inventory"):
        month = body.get("month") or f"synthetic_{counter}_2026"
        fname = body.get("filename") or f"eb_inventory_{month}.xlsx"
        key = f"uscis/{fname}"
        content = _minimal_xlsx("INVENTORY", [
            ["Preference", "Country", "Pending"],
            ["EB-1", "India", 5000 + counter],
        ])
        _register_file(key, fname, content)
        return JSONResponse({
            "ok": True,
            "kind": "uscis_inventory",
            "filename": fname,
            "path_key": key,
            "url": _file_url(key),
            "scan_page": "/uscis/data",
            "publish_counter": counter,
        })

    raise HTTPException(status_code=400, detail=f"unknown kind: {kind!r}")


@app.post("/reset")
def reset():
    """Reset to seed files only (for test isolation)."""
    global _publish_counter
    with _lock:
        _files.clear()
        _publish_counter = 0
    _seed_files()
    return {"ok": True, "message": "reset to seed files"}


def main():
    import uvicorn
    uvicorn.run(app, host=HOST, port=PORT, log_level="info")


if __name__ == "__main__":
    main()
