"""State management for seen postings with atomic file writes."""

import json
import logging
import os
from pathlib import Path
import tempfile
from typing import Iterable, Optional, Set

logger = logging.getLogger(__name__)


def load_seen(path: str | Path) -> Optional[Set[str]]:
    """
    Load seen job IDs from JSON file.
    Returns an empty set if the file does not exist.
    Returns None if the file EXISTS but cannot be parsed — the caller must treat
    that as corruption (never as an empty seen-list, which would re-queue everything).
    Supports either list of IDs or dict with 'seen_ids' or dict keys.
    """
    p = Path(path).resolve()
    if not p.is_file():
        return set()

    try:
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        logger.warning("Error reading seen file at %s: %s", p, e)
        return None

    if isinstance(data, list):
        return {str(x) for x in data if x is not None}
    elif isinstance(data, dict):
        if "seen_ids" in data and isinstance(data["seen_ids"], list):
            return {str(x) for x in data["seen_ids"] if x is not None}
        return {str(k) for k in data.keys() if k is not None}
    # Valid JSON but an unexpected scalar shape: treat as corruption so the
    # caller's backup + baseline re-seed guard applies, not a silent empty set.
    logger.warning("Seen file at %s has unexpected shape %s; treating as corrupt", p, type(data).__name__)
    return None


def save_seen(path: str | Path, seen_ids: Iterable[str]) -> None:
    """
    Save seen job IDs to JSON file with atomic write via temp file + os.replace.
    """
    p = Path(path).resolve()
    p.parent.mkdir(parents=True, exist_ok=True)

    sorted_ids = sorted(list({str(x) for x in seen_ids if x is not None}))

    # Create temporary file in the same directory to ensure same filesystem for os.replace
    fd, tmp_path = tempfile.mkstemp(
        dir=str(p.parent),
        prefix=".seen_",
        suffix=".tmp",
    )

    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(sorted_ids, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, str(p))
    except Exception:
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass
        raise
