"""Config-driven registry of public DOS / USCIS / DHS / DOL data sources.

Each entry describes how to scan a public HTML page for downloadable files,
where to store them, and how they map into engine parsers (auto-discovery).

No secrets; only public government data pages.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence

# Project root (src/ingestion/ -> src/ -> project)
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"

USER_AGENT = (
    "SpilloverEngine-DataScanner/1.0 "
    "(+https://github.com/omairqazi29/gc-ia-visualizer; "
    "public immigration data refresh; polite bot)"
)

REQUEST_DELAY_SEC = 1.0  # polite delay between page/file requests
REQUEST_TIMEOUT_SEC = 45


def _normalize_dos_fsc_name(url: str, link_text: str = "") -> str:
    """Normalize DOS FSC Excel filename; strip URL encoding and _vN suffixes for dedup key."""
    from urllib.parse import unquote

    name = unquote(url.rstrip("/").split("/")[-1].split("?")[0])
    # Keep original DOS casing/spaces; only fix double spaces
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

    base = filename
    base = re.sub(r"_v\d+(\.xlsx?)$", r"\1", base, flags=re.I)
    return " ".join(base.upper().split())


def _uscis_dedup_key(filename: str) -> str:
    import re

    base = filename.lower()
    # Collapse common USCIS naming variants so local/remote don't double-download
    base = base.replace("performancedata", "performance_data")
    base = base.replace("performance-data", "performance_data")
    base = re.sub(r"_v\d+", "", base)
    base = re.sub(r"\.xlsx?$", "", base)
    # Strip trailing version-ish noise; keep fy/q anchors
    return base


@dataclass(frozen=True)
class DataSource:
    """One scannable public data source."""

    source_id: str
    agency: str  # DOS | USCIS | DHS | DOL
    description: str
    scan_url: str
    target_dir: str  # relative to project root, e.g. data/DOS
    # Regex applied to absolute href (and optionally link text)
    link_patterns: Sequence[str]
    # File extensions to accept (lowercase, with dot)
    extensions: Sequence[str] = (".xlsx", ".xls")
    # Filename normalizer: (url, link_text) -> stored filename
    normalize_fn: Callable[[str, str], str] = _normalize_identity
    # Dedup key from stored/local filename
    dedup_key_fn: Callable[[str], str] = lambda f: f.lower()
    # Engine paths / parsers that consume these files
    engine_notes: str = ""
    # Optional schedule hint for docs/workflows
    schedule_hint: str = "weekly"
    # If True, also scan child HTML pages linked from scan_url that match secondary_page_patterns
    follow_links: bool = False
    secondary_page_patterns: Sequence[str] = ()
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
        # Match bulletin HTML pages, not arbitrary assets
        link_patterns=(
            r"visa-bulletin-for-",
            r"/visa-bulletin/\d{4}/visa-bulletin",
        ),
        extensions=(".html",),  # we track bulletin URLs as metadata, not download HTML as data
        normalize_fn=_normalize_identity,
        dedup_key_fn=lambda f: f.lower(),
        engine_notes=(
            "VBPredictor reads data/visa_bulletin/india_eb_history.csv, "
            "india_eb1_history.csv, china_eb1_history.csv — update CSVs when new bulletin posts"
        ),
        schedule_hint="every-3-days",
        tags=("dos", "visa_bulletin", "vb"),
    ),
    "uscis_inventory": DataSource(
        source_id="uscis_inventory",
        agency="USCIS",
        description="USCIS Employment-Based Adjustment of Status (I-485) Inventory",
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
        tags=("uscis", "i140", "pipeline"),
    ),
    "uscis_landing": DataSource(
        source_id="uscis_landing",
        agency="USCIS",
        description=(
            "USCIS Immigration & Citizenship Data landing page — broad scan for "
            "new employment-based xlsx not covered by specific sources"
        ),
        scan_url=(
            "https://www.uscis.gov/tools/reports-and-studies/immigration-and-citizenship-data"
        ),
        target_dir="data",
        link_patterns=(
            r"eb_i140",
            r"i140_rec",
            r"i485_performance",
            r"eb_inventory",
            r"i526.*pref",
        ),
        extensions=(".xlsx", ".xls"),
        normalize_fn=_normalize_uscis_name,
        dedup_key_fn=_uscis_dedup_key,
        engine_notes="Catch-all; files routed by name patterns in data/ or subdirs",
        schedule_hint="weekly",
        tags=("uscis", "catch_all"),
        enabled=False,  # redundant with specific sources; enable for exploratory scans
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
            r"lpr",
            r"table.?7",
            r"liar",
            r"\.xlsx",
        ),
        extensions=(".xlsx", ".xls"),
        normalize_fn=_normalize_uscis_name,
        dedup_key_fn=_uscis_dedup_key,
        engine_notes=(
            "DHSYearbookParser; dhs_eb_category_usage.csv for EB-4/5 spillover totals. "
            "CSV may still need manual/scripted regeneration from new xlsx."
        ),
        schedule_hint="monthly",
        tags=("dhs", "yearbook"),
        enabled=True,
    ),
    "dol_perm": DataSource(
        source_id="dol_perm",
        agency="DOL",
        description="DOL OFLC PERM disclosure data (quarterly)",
        scan_url=(
            "https://www.dol.gov/agencies/eta/foreign-labor/performance"
        ),
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
        tags=("dol", "perm"),
        enabled=True,
    ),
}


# Source groups for CLI / workflow matrix
SOURCE_GROUPS: Dict[str, List[str]] = {
    "all": [s for s, src in SOURCE_REGISTRY.items() if src.enabled],
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
    if source_id not in SOURCE_REGISTRY:
        raise KeyError(
            f"Unknown source_id={source_id!r}. "
            f"Known: {', '.join(sorted(SOURCE_REGISTRY))}"
        )
    return SOURCE_REGISTRY[source_id]


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
    # comma-separated
    parts = [p.strip() for p in source_arg.split(",") if p.strip()]
    out: List[str] = []
    for p in parts:
        if p in SOURCE_GROUPS:
            out.extend(SOURCE_GROUPS[p])
        elif p in SOURCE_REGISTRY:
            out.append(p)
        else:
            raise KeyError(f"Unknown source/group: {p!r}")
    # dedupe preserve order
    seen = set()
    unique = []
    for s in out:
        if s not in seen:
            seen.add(s)
            unique.append(s)
    return unique


def target_path_for(source: DataSource, filename: str) -> Path:
    return PROJECT_ROOT / source.target_dir / filename
