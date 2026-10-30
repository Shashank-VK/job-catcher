"""Catalog loader for watchlist sources."""

from dataclasses import dataclass
import json
import logging
from pathlib import Path
from typing import List, Optional, Set, Tuple

logger = logging.getLogger(__name__)

SUPPORTED_PLATFORMS = ("greenhouse", "ashby", "lever")


@dataclass(frozen=True)
class Board:
    """Represents a job board configuration for a company."""
    company: str
    platform: str
    slug: str


def _parse_companies_data(data: dict, source_label: str) -> List[Board]:
    if not isinstance(data, dict):
        raise ValueError(f"Malformed catalog ({source_label}): root must be a JSON object")
    if "companies" not in data or not isinstance(data["companies"], list):
        raise ValueError(f"Malformed catalog ({source_label}): missing 'companies' list")

    boards: List[Board] = []
    for entry in data["companies"]:
        if not isinstance(entry, dict):
            continue
        company_name = entry.get("name") or "Unknown"
        for platform in SUPPORTED_PLATFORMS:
            slug_list = entry.get(platform, [])
            if not isinstance(slug_list, list):
                continue
            for item in slug_list:
                slug_val = None
                if isinstance(item, dict):
                    slug_val = item.get("slug")
                elif isinstance(item, str):
                    slug_val = item
                if slug_val and isinstance(slug_val, str):
                    slug = slug_val.strip()
                    if slug:
                        boards.append(Board(company=company_name, platform=platform, slug=slug))
    return boards


def load_catalog(
    catalog_path: str | Path,
    secondary_path: Optional[str | Path] = None,
) -> List[Board]:
    """
    Load main watchlist catalog and optional secondary catalog (e.g. xobin_sources.json).
    Dedupes boards by (company, platform, slug) while preserving order.
    """
    main_file = Path(catalog_path).resolve()
    if not main_file.is_file():
        raise FileNotFoundError(f"Main catalog file not found: {main_file}")

    try:
        with open(main_file, "r", encoding="utf-8") as f:
            main_data = json.load(f)
    except json.JSONDecodeError as e:
        raise ValueError(f"Malformed main catalog JSON at {main_file}: {e}") from e

    raw_boards = _parse_companies_data(main_data, str(main_file))

    # Optional secondary catalog
    sec_file: Optional[Path] = None
    if secondary_path is not None:
        sec_file = Path(secondary_path).resolve()
    else:
        # Default adjacent xobin_sources.json
        candidate = main_file.parent / "xobin_sources.json"
        if candidate.is_file():
            sec_file = candidate

    if sec_file is not None and sec_file.is_file():
        try:
            with open(sec_file, "r", encoding="utf-8") as f:
                sec_data = json.load(f)
            sec_boards = _parse_companies_data(sec_data, str(sec_file))
            raw_boards.extend(sec_boards)
        except Exception as e:
            logger.warning("Optional secondary catalog at %s could not be loaded: %s", sec_file, e)

    # Deduplicate by (company, platform, slug) preserving order
    deduped: List[Board] = []
    seen: Set[Tuple[str, str, str]] = set()
    for b in raw_boards:
        key = (b.company, b.platform, b.slug)
        if key not in seen:
            seen.add(key)
            deduped.append(b)

    return deduped
