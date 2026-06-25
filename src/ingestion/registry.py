"""Config-driven registry of public DOS / USCIS / DHS / DOL data sources.

Each entry describes how to scan a public HTML page for downloadable files,
where to store them, and how they map into engine parsers (auto-discovery).

No secrets; only public government data pages.

v1 scope: supply-critical + pipeline sources are enabled. Additional sources
(NVC, CEAC, H1B, processing times, monthly I-485 CSVs) are registered as
disabled stubs for completeness — enable when scan URLs/patterns are stable.

Optional env overrides (opt-in; no behavior change unless set — used by e2e/mock tests):
  INGESTION_PROJECT_ROOT       — override project root for path resolution
  INGESTION_DATA_DIR           — override data/ write/read directory
  INGESTION_SOURCE_URL_OVERRIDES — JSON map {source_id: scan_url}
  INGESTION_SOURCE_URL_<id>    — per-source scan URL (id uppercased, hyphens→underscores)
  INGESTION_EXTRA_ALLOWED_HOSTS — comma-separated hosts added to every source allowlist
  INGESTION_REQUEST_DELAY_SEC  — override polite delay (e.g. 0 for fast local e2e)
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence, Tuple

# Project root (src/ingestion/ -> src/ -> project)
_DEFAULT_PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _resolve_project_root() -> Path:
    override = os.environ.get("INGESTION_PROJECT_ROOT", "").strip()
    if override:
        return Path(override).expanduser().resolve()
    return _DEFAULT_PROJECT_ROOT


def _resolve_data_dir(project_root: Path) -> Path:
    override = os.environ.get("INGESTION_DATA_DIR", "").strip()
    if override:
        return Path(override).expanduser().resolve()
    return project_root / "data"


PROJECT_ROOT = _resolve_project_root()
DATA_DIR = _resolve_data_dir(PROJECT_ROOT)

USER_AGENT = (
    "SpilloverEngine-DataScanner/1.0 "
    "(+https://github.com/omairqazi29/visualizer; "
    "public immigration data refresh; polite bot)"
)

REQUEST_DELAY_SEC = 1.0  # polite delay between page/file requests
REQUEST_TIMEOUT_SEC = 45

# Allow e2e/mock runs to skip the polite delay without code changes.
_delay_override = os.environ.get("INGESTION_REQUEST_DELAY_SEC", "").strip()
if _delay_override:
    try:
        REQUEST_DELAY_SEC = float(_delay_override)
    except ValueError:
        pass


def _extra_allowed_hosts() -> Tuple[str, ...]:
    """Hosts appended to every source allowlist when INGESTION_EXTRA_ALLOWED_HOSTS is set."""
    raw = os.environ.get("INGESTION_EXTRA_ALLOWED_HOSTS", "").strip()
    if not raw:
        return ()
    return tuple(h.strip() for h in raw.split(",") if h.strip())


def _source_url_overrides() -> Dict[str, str]:
    """Merge INGESTION_SOURCE_URL_OVERRIDES JSON + INGESTION_SOURCE_URL_<SOURCE_ID> envs."""
    overrides: Dict[str, str] = {}
    raw_json = os.environ.get("INGESTION_SOURCE_URL_OVERRIDES", "").strip()
    if raw_json:
        try:
            parsed = json.loads(raw_json)
            if isinstance(parsed, dict):
                for k, v in parsed.items():
                    if k and v:
                        overrides[str(k)] = str(v)
        except json.JSONDecodeError:
            pass
    prefix = "INGESTION_SOURCE_URL_"
    for key, val in os.environ.items():
        if not key.startswith(prefix) or key == "INGESTION_SOURCE_URL_OVERRIDES":
            continue
        if not val or not val.strip():
            continue
        sid = key[len(prefix) :].lower()
        overrides[sid] = val.strip()
    return overrides


def refresh_paths_from_env() -> None:
    """Re-read PROJECT_ROOT / DATA_DIR from env (for tests that set env after import)."""
    global PROJECT_ROOT, DATA_DIR
    PROJECT_ROOT = _resolve_project_root()
    DATA_DIR = _resolve_data_dir(PROJECT_ROOT)
    # Keep security module in sync if already imported
    try:
        from . import security

        security.PROJECT_ROOT = PROJECT_ROOT
        security.DATA_DIR = DATA_DIR
    except Exception:  # noqa: BLE001
        pass


def _normalize_dos_fsc_name(url: str, link_text: str = "") -> str:
    """Normalize DOS FSC Excel filename; strip URL encoding."""
    from urllib.parse import unquote

    name = unquote(url.rstrip("/").split("/")[-1].split("?")[0])
    name = " ".join(name.split())
    return name


def _normalize_uscis_name(url: str, link_text: str = "") -> str:
    """Lowercase USCIS report filenames (site convention)."""
    from urllib.parse import unquote

    name = unquote(url.rstrip("/").split("/")[-1].split("?")[0])
    return name.lower().replace(" ", "_")


def _normalize_identity(url: str, link_text: str = "") -> str:
    from urllib.parse import unquote

    return unquote(url.rstrip("/").split("/")[-1].split("?")[0])


def _dos_dedup_key(filename: str) -> str:
    """Strip _v1/_v2 suffix and normalize case/spaces for DOS duplicate detection."""
    import re

    base = re.sub(r"_v\d+(\.xlsx?)$", r"\1", filename, flags=re.I)
    return " ".join(base.upper().split())


def _uscis_dedup_key(filename: str) -> str:
    """Normalize USCIS names: performancedata variants + strip _vN only.

    Intentionally does NOT fuzzy-merge distinct form prefixes (eb_i140 vs i140_rec).
    """
    import re

    base = filename.lower()
    base = base.replace("performancedata", "performance_data")
    base = base.replace("performance-data", "performance_data")
    base = re.sub(r"_v\d+", "", base)
    base = re.sub(r"\.xlsx?$", "", base)
    return base


def uscis_names_equivalent(a: str, b: str) -> bool:
    """True only when names differ by performance_data/performancedata or _vN only."""
    return _uscis_dedup_key(a) == _uscis_dedup_key(b)


@dataclass(frozen=True)
class DataSource:
    """One scannable public data source."""

    source_id: str
    agency: str  # DOS | USCIS | DHS | DOL | OTHER
    description: str
    scan_url: str
    target_dir: str  # relative to project root, e.g. data/DOS
    link_patterns: Sequence[str]
    extensions: Sequence[str] = (".xlsx", ".xls")
    normalize_fn: Callable[[str, str], str] = _normalize_identity
    dedup_key_fn: Callable[[str], str] = lambda f: f.lower()
    engine_notes: str = ""
    schedule_hint: str = "weekly"
    # Follow same-host HTML links matching secondary_page_patterns (max depth 1)
    follow_links: bool = False
    secondary_page_patterns: Sequence[str] = ()
    # Host allowlist for scan + download (subdomains allowed)
    allowed_hosts: Sequence[str] = ()
    enabled: bool = True
    tags: Sequence[str] = field(default_factory=tuple)


# ── Source registry ──────────────────────────────────────────────────────────

SOURCE_REGISTRY: Dict[str, DataSource] = {
    "dos_iv_fsc": DataSource(
        source_id="dos_iv_fsc",
        agency="DOS",
        description="DOS Monthly IV Issuances by FSC or Place of Birth and Visa Class (Excel)",
        scan_url=(
            "https://travel.state.gov/content/travel/en/legal/visa-law0/"
            "visa-statistics/immigrant-visa-statistics/monthly-immigrant-visa-issuances.html"
        ),
        target_dir="data/DOS",
        link_patterns=(
            r"IV\s*Issuances\s*by\s*FSC",
            r"FSC\s*or\s*Place\s*of\s*Birth",
            r"MonthlyIVIssuances.*FSC",
        ),
        extensions=(".xlsx", ".xls"),
        normalize_fn=_normalize_dos_fsc_name,
        dedup_key_fn=_dos_dedup_key,
        engine_notes=(
            "DOSParser.load_from_directory(data/DOS/) — consular IV issuances; "
            "ground truth for restriction savings / FB usage in supply.py"
        ),
        schedule_hint="twice-weekly",
        allowed_hosts=("travel.state.gov", "state.gov"),
        tags=("dos", "iv", "supply"),
    ),
    "visa_bulletin": DataSource(
        source_id="visa_bulletin",
        agency="DOS",
        description=(
            "DOS Visa Bulletin index — detects new monthly bulletin HTML pages "
            "(manual/semi-auto CSV update of data/visa_bulletin/*_history.csv)"
        ),
        scan_url=(
            "https://travel.state.gov/content/travel/en/legal/visa-law0/visa-bulletin.html"
        ),
        target_dir="data/visa_bulletin",
        link_patterns=(
            r"visa-bulletin-for-",
            r"/visa-bulletin/\d{4}/visa-bulletin",
        ),
        extensions=(".html",),
        normalize_fn=_normalize_identity,
        dedup_key_fn=lambda f: f.lower(),
        engine_notes=(
            "VBPredictor reads data/visa_bulletin/india_eb_history.csv, "
            "india_eb1_history.csv, china_eb1_history.csv — update CSVs when new bulletin posts"
        ),
        schedule_hint="every-3-days",
        allowed_hosts=("travel.state.gov", "state.gov"),
        # Owned by data-scan-visa-bulletin.yml; excluded from main `all` group
        tags=("dos", "visa_bulletin", "vb"),
    ),
    "uscis_inventory": DataSource(
        source_id="uscis_inventory",
        agency="USCIS",
        description=(
            "USCIS Employment-Based Adjustment of Status (I-485) Inventory. "
            "NOTE: often NOT listed on the main landing page; follow_links scans "
            "report subpages; may still require manual drop into data/."
        ),
        scan_url=(
            "https://www.uscis.gov/tools/reports-and-studies/immigration-and-citizenship-data"
        ),
        target_dir="data",
        link_patterns=(
            r"eb_inventory",
            r"inventory.*i.?485",
            r"i.?485.*inventory",
            r"employment.?based.*inventory",
            r"adjustment.?of.?status.?inventory",
        ),
        extensions=(".xlsx", ".xls"),
        normalize_fn=_normalize_uscis_name,
        dedup_key_fn=_uscis_dedup_key,
        engine_notes=(
            "InventoryParser via data_discovery.get_latest_inventory_path() — "
            "eb_inventory_*.xlsx drives demand/queue + non-India EB-1 demand"
        ),
        schedule_hint="weekly",
        follow_links=True,
        secondary_page_patterns=(
            r"/tools/reports",
            r"/reports-and-studies",
            r"immigration-and-citizenship",
            r"employment",
            r"inventory",
            r"i-485",
            r"i485",
        ),
        allowed_hosts=("uscis.gov", "www.uscis.gov", "egov.uscis.gov"),
        tags=("uscis", "inventory", "i485", "demand"),
    ),
    "uscis_i485_perf": DataSource(
        source_id="uscis_i485_perf",
        agency="USCIS",
        description="USCIS I-485 Performance / Performance Data (quarterly)",
        scan_url=(
            "https://www.uscis.gov/tools/reports-and-studies/immigration-and-citizenship-data"
        ),
        target_dir="data/USCIS_I485",
        link_patterns=(
            r"i485_performance",
            r"i485_performancedata",
            r"i485_performance_data",
            r"i-485.*performance",
        ),
        extensions=(".xlsx", ".xls"),
        normalize_fn=_normalize_uscis_name,
        dedup_key_fn=_uscis_dedup_key,
        engine_notes=(
            "I485FlowParser / I-485 performance files in data/USCIS_I485/ — "
            "inflow vs outflow for I-485 queue trends"
        ),
        schedule_hint="weekly",
        allowed_hosts=("uscis.gov", "www.uscis.gov"),
        tags=("uscis", "i485", "performance"),
    ),
    "uscis_i140": DataSource(
        source_id="uscis_i140",
        agency="USCIS",
        description="USCIS I-140 receipts and EB I-140/I-360/I-526 performance pipeline data",
        scan_url=(
            "https://www.uscis.gov/tools/reports-and-studies/immigration-and-citizenship-data"
        ),
        target_dir="data",
        link_patterns=(
            r"eb_i140_i360_i526",
            r"i140_rec_by_class_country",
            r"i140_rec_",
            r"i140_.*performance",
        ),
        extensions=(".xlsx", ".xls"),
        normalize_fn=_normalize_uscis_name,
        dedup_key_fn=_uscis_dedup_key,
        engine_notes=(
            "PipelineParser / I140ReceiptsParser via data_discovery — "
            "eb_i140_* and i140_rec_* in data/ for pipeline backlog + new filings"
        ),
        schedule_hint="weekly",
        allowed_hosts=("uscis.gov", "www.uscis.gov"),
        tags=("uscis", "i140", "pipeline"),
    ),
    "uscis_landing": DataSource(
        source_id="uscis_landing",
        agency="USCIS",
        description="USCIS landing page catch-all (redundant; disabled)",
        scan_url=(
            "https://www.uscis.gov/tools/reports-and-studies/immigration-and-citizenship-data"
        ),
        target_dir="data",
        link_patterns=(r"eb_i140", r"i140_rec", r"i485_performance", r"eb_inventory"),
        extensions=(".xlsx", ".xls"),
        normalize_fn=_normalize_uscis_name,
        dedup_key_fn=_uscis_dedup_key,
        engine_notes="Catch-all; files routed by name patterns in data/ or subdirs",
        schedule_hint="weekly",
        allowed_hosts=("uscis.gov", "www.uscis.gov"),
        tags=("uscis", "catch_all"),
        enabled=False,
    ),
    "dhs_yearbook": DataSource(
        source_id="dhs_yearbook",
        agency="DHS",
        description="DHS OHSS Immigration / Yearbook / LIAR reports (if linked as xlsx)",
        scan_url="https://ohss.dhs.gov/topics/immigration/yearbook",
        target_dir="data/DHS_Yearbook",
        link_patterns=(
            r"yearbook",
            r"lawful.?permanent",
            r"\blpr\b",
            r"table.?7",
            r"\bliar\b",
            r"immigration.?statistics",
        ),
        extensions=(".xlsx", ".xls"),
        normalize_fn=_normalize_uscis_name,
        dedup_key_fn=_uscis_dedup_key,
        engine_notes=(
            "DHSYearbookParser; dhs_eb_category_usage.csv for EB-4/5 spillover totals. "
            "CSV may still need manual/scripted regeneration from new xlsx."
        ),
        schedule_hint="monthly",
        follow_links=True,
        secondary_page_patterns=(r"yearbook", r"immigration", r"statistics", r"table"),
        allowed_hosts=("ohss.dhs.gov", "dhs.gov", "www.dhs.gov"),
        tags=("dhs", "yearbook"),
        enabled=True,
    ),
    "dol_perm": DataSource(
        source_id="dol_perm",
        agency="DOL",
        description="DOL OFLC PERM disclosure data (quarterly)",
        scan_url="https://www.dol.gov/agencies/eta/foreign-labor/performance",
        target_dir="data/DOL_PERM",
        link_patterns=(
            r"PERM.?Disclosure",
            r"perm_disclosure",
            r"PERM_Disclosure_Data",
        ),
        extensions=(".xlsx", ".xls", ".zip"),
        normalize_fn=_normalize_identity,
        dedup_key_fn=lambda f: f.lower(),
        engine_notes="PERMParser — leading indicator for EB-2/EB-3 I-140 filings",
        schedule_hint="monthly",
        allowed_hosts=("dol.gov", "www.dol.gov"),
        tags=("dol", "perm"),
        enabled=True,
    ),
    # ── Disabled stubs (v1 completeness; enable when patterns stabilize) ──
    "nvc_waiting_list": DataSource(
        source_id="nvc_waiting_list",
        agency="DOS",
        description="NVC / ARIVA waiting list PDFs (disabled stub — no stable automated URL)",
        scan_url="https://travel.state.gov/content/travel/en/us-visas/immigrate/nvc-timeframes.html",
        target_dir="data/NVC",
        link_patterns=(r"WaitingList", r"ARIVA", r"IV_Report", r"waiting.?list"),
        extensions=(".pdf", ".csv"),
        engine_notes="NVCParser reads data/NVC/ CSVs; PDFs often need semi-manual extraction",
        allowed_hosts=("travel.state.gov", "state.gov"),
        enabled=False,
        tags=("dos", "nvc", "stub"),
    ),
    "uscis_i485_monthly_csv": DataSource(
        source_id="uscis_i485_monthly_csv",
        agency="USCIS",
        description="USCIS I-485 monthly flow CSVs (disabled stub)",
        scan_url=(
            "https://www.uscis.gov/tools/reports-and-studies/immigration-and-citizenship-data"
        ),
        target_dir="data/USCIS_I485",
        link_patterns=(r"monthly_.*\.csv", r"i485.*monthly"),
        extensions=(".csv",),
        engine_notes="I485FlowParser — monthly_*.csv in data/USCIS_I485/",
        allowed_hosts=("uscis.gov", "www.uscis.gov"),
        enabled=False,
        tags=("uscis", "i485", "stub"),
    ),
    "uscis_processing_times": DataSource(
        source_id="uscis_processing_times",
        agency="USCIS",
        description="USCIS processing times (disabled stub — often JS/API driven)",
        scan_url="https://egov.uscis.gov/processing-times/",
        target_dir="data/USCIS_ProcessingTimes",
        link_patterns=(r"processing.?time", r"i-485"),
        extensions=(".csv", ".json", ".xlsx"),
        engine_notes="ProcessingTimesParser — eb_i485_processing_times.csv",
        allowed_hosts=("egov.uscis.gov", "uscis.gov"),
        enabled=False,
        tags=("uscis", "processing_times", "stub"),
    ),
    "ceac_scheduling": DataSource(
        source_id="ceac_scheduling",
        agency="OTHER",
        description="CEAC consular scheduling snapshots (disabled stub — third-party/API)",
        scan_url="https://ceac.state.gov/CEAC/",
        target_dir="data/CEAC",
        link_patterns=(r"ceac",),
        extensions=(".json", ".ndjson"),
        engine_notes="CEACParser — data/CEAC/ ndjson/json snapshots",
        allowed_hosts=("ceac.state.gov", "state.gov"),
        enabled=False,
        tags=("ceac", "stub"),
    ),
    "h1b_data": DataSource(
        source_id="h1b_data",
        agency="USCIS",
        description="H-1B registration/approval aggregates (disabled stub)",
        scan_url=(
            "https://www.uscis.gov/tools/reports-and-studies/immigration-and-citizenship-data"
        ),
        target_dir="data/H1B",
        link_patterns=(r"h.?1b", r"h1b"),
        extensions=(".csv", ".xlsx"),
        engine_notes="H1BParser — data/H1B/*.csv",
        allowed_hosts=("uscis.gov", "www.uscis.gov"),
        enabled=False,
        tags=("h1b", "stub"),
    ),
}


# Source groups for CLI / workflow matrix
# NOTE: `all` excludes visa_bulletin (owned by data-scan-visa-bulletin.yml) and
# dol_perm (large multi-year OFLC archives; use `dol` explicitly to avoid noisy PRs).
_ENABLED_CORE = [
    s
    for s, src in SOURCE_REGISTRY.items()
    if src.enabled and s not in ("visa_bulletin", "dol_perm")
]

SOURCE_GROUPS: Dict[str, List[str]] = {
    "all": list(_ENABLED_CORE),
    "all_with_dol": list(_ENABLED_CORE) + ["dol_perm"],
    "all_including_vb": [s for s, src in SOURCE_REGISTRY.items() if src.enabled],
    "dos": ["dos_iv_fsc"],
    "dos_iv": ["dos_iv_fsc"],
    "visa_bulletin": ["visa_bulletin"],
    "vb": ["visa_bulletin"],
    "uscis": ["uscis_inventory", "uscis_i485_perf", "uscis_i140"],
    "uscis_inventory": ["uscis_inventory"],
    "uscis_i485_perf": ["uscis_i485_perf"],
    "uscis_i140": ["uscis_i140"],
    "dhs": ["dhs_yearbook"],
    "dol": ["dol_perm"],
    "supply": ["dos_iv_fsc", "uscis_inventory", "uscis_i140"],
}


def get_source(source_id: str) -> DataSource:
    """Return a source, applying opt-in env URL/host overrides when set."""
    if source_id not in SOURCE_REGISTRY:
        raise KeyError(
            f"Unknown source_id={source_id!r}. "
            f"Known: {', '.join(sorted(SOURCE_REGISTRY))}"
        )
    src = SOURCE_REGISTRY[source_id]
    url_overrides = _source_url_overrides()
    extra_hosts = _extra_allowed_hosts()
    if not url_overrides and not extra_hosts:
        return src

    new_url = url_overrides.get(source_id, src.scan_url)
    new_hosts = tuple(src.allowed_hosts or ())
    if extra_hosts:
        # Preserve order, avoid dupes
        seen = set(h.lower() for h in new_hosts)
        merged = list(new_hosts)
        for h in extra_hosts:
            if h.lower() not in seen:
                merged.append(h)
                seen.add(h.lower())
        new_hosts = tuple(merged)

    if new_url == src.scan_url and new_hosts == tuple(src.allowed_hosts or ()):
        return src
    return replace(src, scan_url=new_url, allowed_hosts=new_hosts)


def list_sources(enabled_only: bool = True) -> List[DataSource]:
    items = list(SOURCE_REGISTRY.values())
    if enabled_only:
        items = [s for s in items if s.enabled]
    return items


def resolve_source_ids(source_arg: Optional[str]) -> List[str]:
    """Resolve CLI/workflow source flag to concrete source_id list."""
    if not source_arg or source_arg in ("all", "*"):
        return list(SOURCE_GROUPS["all"])
    if source_arg in SOURCE_GROUPS:
        return list(SOURCE_GROUPS[source_arg])
    if source_arg in SOURCE_REGISTRY:
        return [source_arg]
    parts = [p.strip() for p in source_arg.split(",") if p.strip()]
    out: List[str] = []
    for p in parts:
        if p in SOURCE_GROUPS:
            out.extend(SOURCE_GROUPS[p])
        elif p in SOURCE_REGISTRY:
            out.append(p)
        else:
            raise KeyError(f"Unknown source/group: {p!r}")
    seen = set()
    unique = []
    for s in out:
        if s not in seen:
            seen.add(s)
            unique.append(s)
    return unique


def target_path_for(source: DataSource, filename: str) -> Path:
    """Build safe target path under source.target_dir (rejects traversal).

    When INGESTION_DATA_DIR is set, ``data/…`` targets are remapped under that
    isolated data root so e2e/mock runs never write into the real ``data/`` tree.
    """
    from .security import safe_target_path

    target_dir = PROJECT_ROOT / source.target_dir
    data_override = os.environ.get("INGESTION_DATA_DIR", "").strip()
    if data_override and source.target_dir.startswith("data"):
        # data/DOS -> <INGESTION_DATA_DIR>/DOS ; data -> <INGESTION_DATA_DIR>
        suffix = source.target_dir[len("data") :].lstrip("/\\")
        target_dir = DATA_DIR / suffix if suffix else DATA_DIR
    return safe_target_path(target_dir, filename)
