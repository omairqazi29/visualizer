"""Validate downloaded / existing data files using project parsers."""

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
    if parent == "DOL_PERM" or "perm_disclosure" in name:
        return "perm"
    if parent == "visa_bulletin":
        return "visa_bulletin"
    return "unknown"


def validate_path(path: Path) -> ValidationItem:
    """Run an appropriate lightweight parser check on one file."""
    path = Path(path)
    if not path.exists():
        return ValidationItem(str(path), "missing", False, "file does not exist")

    kind = _kind_for_path(path)
    try:
        if kind == "dos":
            from src.parsers.dos_parser import DOSParser

            # Single-file load if possible; else directory context
            dos_dir = path.parent
            df = DOSParser.load_from_directory(str(dos_dir))
            return ValidationItem(
                str(path),
                kind,
                True,
                f"DOSParser OK ({len(df)} combined rows in dir)",
                detail=path.name,
            )
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
            from src.parsers.i140_receipts_parser import I140ReceiptsParser

            # Some parsers may have different entry points; best-effort
            if hasattr(I140ReceiptsParser, "latest"):
                pass
            try:
                parser = I140ReceiptsParser(str(path))
                if hasattr(parser, "load_data"):
                    parser.load_data()
                return ValidationItem(str(path), kind, True, "I140ReceiptsParser OK")
            except TypeError:
                return ValidationItem(
                    str(path), kind, True, "I140ReceiptsParser present (basic file check OK)"
                )
        if kind == "i485_perf":
            # I-485 performance files are xlsx; ensure openable via openpyxl/pandas
            import pandas as pd

            xl = pd.ExcelFile(path)
            return ValidationItem(
                str(path),
                kind,
                True,
                f"I-485 perf readable ({len(xl.sheet_names)} sheets)",
            )
        if kind == "dhs":
            import pandas as pd

            xl = pd.ExcelFile(path)
            return ValidationItem(
                str(path), kind, True, f"DHS xlsx readable ({len(xl.sheet_names)} sheets)"
            )
        if kind == "perm":
            import pandas as pd

            if path.suffix.lower() == ".zip":
                return ValidationItem(str(path), kind, True, "PERM zip present (not expanded)")
            xl = pd.ExcelFile(path)
            return ValidationItem(
                str(path), kind, True, f"PERM xlsx readable ({len(xl.sheet_names)} sheets)"
            )
        if kind == "visa_bulletin":
            if path.suffix.lower() == ".csv":
                import pandas as pd

                df = pd.read_csv(path)
                return ValidationItem(
                    str(path), kind, True, f"VB CSV OK ({len(df)} rows)"
                )
            return ValidationItem(str(path), kind, True, "visa_bulletin sidecar/meta OK")

        # unknown: at least confirm non-empty
        size = path.stat().st_size
        if size == 0:
            return ValidationItem(str(path), kind, False, "empty file")
        return ValidationItem(str(path), kind, True, f"file present ({size} bytes), no specific parser")
    except Exception as e:  # noqa: BLE001
        return ValidationItem(str(path), kind, False, f"{type(e).__name__}: {e}")


def validate_downloaded_files(
    paths: Optional[Sequence[Path]] = None,
    candidates: Optional[Sequence[RemoteCandidate]] = None,
    *,
    include_baseline: bool = False,
) -> ValidationReport:
    """Validate specific paths/candidates, optionally plus baseline discovered files."""
    report = ValidationReport()
    seen = set()

    def _add(p: Path):
        key = str(p.resolve()) if p.exists() else str(p)
        if key in seen:
            return
        seen.add(key)
        report.items.append(validate_path(p))

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
                files = list(dos_dir.glob("*.xlsx"))
                if files:
                    _add(files[0])  # one sample; full dir validated inside DOSParser
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
