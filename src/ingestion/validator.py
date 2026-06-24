"""Validate downloaded / existing data files using project parsers.

This is a QA gate for data quality — not a security boundary. Security checks
(path allowlist, host allowlist, size limits) happen in scanner/fetcher/security.
In PR mode, unknown kinds and paths outside data/ fail closed.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Sequence

# Ensure project root on path
_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from .registry import DATA_DIR, PROJECT_ROOT
from .scanner import RemoteCandidate
from .security import is_under_data_dir


@dataclass
class ValidationItem:
    path: str
    kind: str
    ok: bool
    message: str = ""
    detail: str = ""

    def to_dict(self) -> dict:
        return {
            "path": self.path,
            "kind": self.kind,
            "ok": self.ok,
            "message": self.message,
            "detail": self.detail,
        }


@dataclass
class ValidationReport:
    items: List[ValidationItem] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return all(i.ok for i in self.items) if self.items else True

    def to_dict(self) -> dict:
        return {"ok": self.ok, "items": [i.to_dict() for i in self.items]}


def _kind_for_path(path: Path) -> str:
    name = path.name.lower()
    parent = path.parent.name
    if parent == "DOS" or "IV Issuances by FSC" in path.name:
        return "dos"
    if name.startswith("eb_inventory"):
        return "inventory"
    if "i485_performance" in name or "i485_performancedata" in name:
        return "i485_perf"
    if "i140_rec" in name:
        return "i140_receipts"
    if "eb_i140" in name or ("performance" in name and "i140" in name):
        return "pipeline"
    if parent == "DHS_Yearbook":
        return "dhs"
    if parent == "DOL_PERM" or "perm_disclosure" in name.lower() or "perm_disclosure" in name:
        return "perm"
    if parent == "visa_bulletin":
        return "visa_bulletin"
    if name == ".seen_bulletins.txt":
        return "visa_bulletin"
    return "unknown"


def _validate_xlsx_openable(path: Path, kind: str, label: str) -> ValidationItem:
    import pandas as pd

    xl = pd.ExcelFile(path)
    if not xl.sheet_names:
        return ValidationItem(str(path), kind, False, f"{label}: no sheets")
    return ValidationItem(
        str(path), kind, True, f"{label} readable ({len(xl.sheet_names)} sheets)"
    )


def validate_path(path: Path, *, strict_unknown: bool = False) -> ValidationItem:
    """Run an appropriate lightweight parser check on one file.

    Args:
        strict_unknown: if True, kind==unknown fails (use in PR mode).
    """
    path = Path(path)
    if not path.exists():
        return ValidationItem(str(path), "missing", False, "file does not exist")

    if path.is_file() and path.stat().st_size == 0:
        return ValidationItem(str(path), _kind_for_path(path), False, "empty file")

    kind = _kind_for_path(path)
    try:
        if kind == "dos":
            # Validate THIS file specifically first (not whole dir — avoids masking corrupt new file)
            item = _validate_xlsx_openable(path, kind, "DOS xlsx")
            if not item.ok:
                return item
            # Try single-file DOSParser load
            try:
                from src.parsers.dos_parser import DOSParser

                parser = DOSParser(str(path))
                if hasattr(parser, "load_data"):
                    df = parser.load_data()
                    if df is not None and hasattr(df, "__len__") and len(df) == 0:
                        return ValidationItem(
                            str(path), kind, False, "DOSParser returned 0 rows for this file"
                        )
                    n = len(df) if df is not None and hasattr(df, "__len__") else "?"
                    return ValidationItem(
                        str(path), kind, True, f"DOSParser single-file OK ({n} rows)", detail=path.name
                    )
            except Exception as e:  # noqa: BLE001
                # openpyxl passed; parser may still fail on schema — report failure strictly
                return ValidationItem(
                    str(path), kind, False, f"DOSParser single-file failed: {type(e).__name__}: {e}"
                )
            return item

        if kind == "inventory":
            from src.parsers.inventory_parser import InventoryParser

            p = InventoryParser(str(path))
            stats = p.get_india_eb1_queue()
            return ValidationItem(
                str(path),
                kind,
                True,
                f"InventoryParser OK (India EB-1 total={stats.get('total', '?')})",
            )

        if kind == "pipeline":
            from src.parsers.pipeline_parser import PipelineParser

            pp = PipelineParser(str(path))
            pp.load_data()
            return ValidationItem(str(path), kind, True, "PipelineParser load_data OK")

        if kind == "i140_receipts":
            # Strict: must open as xlsx; try parser if constructible
            item = _validate_xlsx_openable(path, kind, "I-140 receipts xlsx")
            if not item.ok:
                return item
            try:
                from src.parsers.i140_receipts_parser import I140ReceiptsParser

                parser = I140ReceiptsParser(str(path))
                if hasattr(parser, "load_data"):
                    parser.load_data()
                return ValidationItem(str(path), kind, True, "I140ReceiptsParser OK")
            except Exception as e:  # noqa: BLE001
                return ValidationItem(
                    str(path),
                    kind,
                    False,
                    f"I140ReceiptsParser failed: {type(e).__name__}: {e}",
                )

        if kind == "i485_perf":
            return _validate_xlsx_openable(path, kind, "I-485 perf")

        if kind == "dhs":
            return _validate_xlsx_openable(path, kind, "DHS xlsx")

        if kind == "perm":
            if path.suffix.lower() == ".zip":
                size = path.stat().st_size
                if size == 0:
                    return ValidationItem(str(path), kind, False, "empty zip")
                return ValidationItem(str(path), kind, True, f"PERM zip present ({size} bytes)")
            return _validate_xlsx_openable(path, kind, "PERM xlsx")

        if kind == "visa_bulletin":
            if path.suffix.lower() == ".csv":
                import pandas as pd

                df = pd.read_csv(path)
                return ValidationItem(str(path), kind, True, f"VB CSV OK ({len(df)} rows)")
            if path.name == ".seen_bulletins.txt":
                return ValidationItem(str(path), kind, True, "visa_bulletin sidecar OK")
            return ValidationItem(str(path), kind, True, "visa_bulletin meta OK")

        # unknown
        size = path.stat().st_size
        if strict_unknown:
            return ValidationItem(
                str(path),
                kind,
                False,
                f"unknown kind refused in strict/PR mode ({size} bytes)",
            )
        return ValidationItem(
            str(path), kind, True, f"file present ({size} bytes), no specific parser (QA-only)"
        )
    except Exception as e:  # noqa: BLE001
        return ValidationItem(str(path), kind, False, f"{type(e).__name__}: {e}")


def validate_downloaded_files(
    paths: Optional[Sequence[Path]] = None,
    candidates: Optional[Sequence[RemoteCandidate]] = None,
    *,
    include_baseline: bool = False,
    strict_unknown: bool = False,
    require_under_data: bool = False,
) -> ValidationReport:
    """Validate specific paths/candidates, optionally plus baseline discovered files.

    Args:
        strict_unknown: fail unknown kinds (PR mode).
        require_under_data: fail paths outside data/ (PR mode).
    """
    report = ValidationReport()
    seen = set()

    def _add(p: Path):
        key = str(p.resolve()) if p.exists() else str(p)
        if key in seen:
            return
        seen.add(key)
        if require_under_data and p.exists() and not is_under_data_dir(p):
            report.items.append(
                ValidationItem(str(p), "security", False, "path outside data/ refused")
            )
            return
        report.items.append(validate_path(p, strict_unknown=strict_unknown))

    if candidates:
        for c in candidates:
            if c.target_path and c.content_type == "file":
                _add(Path(c.target_path))

    if paths:
        for p in paths:
            _add(Path(p))

    if include_baseline:
        try:
            from src.data_discovery import (
                get_dos_dir,
                get_latest_inventory_path,
                get_latest_pipeline_path,
            )

            dos_dir = Path(get_dos_dir())
            if dos_dir.exists():
                files = sorted(dos_dir.glob("*.xlsx"))
                if files:
                    _add(files[-1])  # newest by name-ish
            inv = Path(get_latest_inventory_path())
            if inv.exists():
                _add(inv)
            pipe = Path(get_latest_pipeline_path())
            if pipe.exists():
                _add(pipe)
        except Exception as e:  # noqa: BLE001
            report.items.append(
                ValidationItem("baseline", "baseline", False, f"baseline discovery failed: {e}")
            )

    return report


def summarize_validation(report: ValidationReport) -> str:
    lines = ["=== Validation Summary ===", f"overall_ok={report.ok}"]
    for i in report.items:
        tag = "OK" if i.ok else "FAIL"
        lines.append(f"  [{tag}] ({i.kind}) {Path(i.path).name}: {i.message}")
    return "\n".join(lines)
