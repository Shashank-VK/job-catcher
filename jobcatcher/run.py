"""Poll cycle orchestration for job-catcher."""

from dataclasses import dataclass
import logging
from pathlib import Path
import time
from typing import Any, Callable, Dict, List, Optional, Set

from .catalog import Board, load_catalog
from .fetch import FetchResult, Posting, fetch_board
from .filter import FilterResult, filter_posting
from .queue import (
    append_run_log,
    append_to_queue,
    make_queue_record,
    make_run_log_record,
    now_ist_iso,
)
from .state import load_seen, save_seen
from .triage import OmniRouteClient, TriageResult, triage_posting

logger = logging.getLogger(__name__)

DEFAULT_CATALOG_PATH = Path.home() / "workspace/goals/land-a-ds-ml-internship-or-job/hidden_files/watchlist_sources.json"
DEFAULT_STATE_DIR = Path.home() / "workspace/goals/land-a-ds-ml-internship-or-job/hidden_files"
DEFAULT_RUNS_LOG_PATH = Path(__file__).resolve().parent.parent / "job-catcher-runs.jsonl"


def posting_key(p: Posting) -> str:
    """Composite seen-list identity: platform:slug:job_id.

    Bare job_ids are only unique within one board — Greenhouse IDs are per-board
    numerics, so keying on job_id alone silently drops other companies' postings.
    """
    return f"{p.platform}:{p.slug}:{p.job_id}"


@dataclass
class CycleResult:
    """Summary of a completed poll cycle."""
    boards_ok: int
    boards_failed: int
    postings_seen: int
    postings_new: int
    postings_queued: int
    baseline_run: bool
    duration_seconds: float


def run_cycle(
    catalog_path: Optional[str | Path] = None,
    secondary_catalog_path: Optional[str | Path] = None,
    state_dir: Optional[str | Path] = None,
    runs_log_path: Optional[str | Path] = None,
    no_baseline: bool = False,
    polite_delay: float = 0.3,
    triage_client: Optional[OmniRouteClient] = None,
    boards: Optional[List[Board]] = None,
    fetch_board_fn: Optional[Callable[[Board], FetchResult]] = None,
) -> CycleResult:
    """
    Run one poll cycle orchestrating catalog -> fetch -> diff -> filter -> triage -> queue.
    """
    start_time = time.time()
    cycle_time = now_ist_iso()

    c_path = Path(catalog_path) if catalog_path else DEFAULT_CATALOG_PATH
    s_dir = Path(state_dir) if state_dir else DEFAULT_STATE_DIR
    r_path = Path(runs_log_path) if runs_log_path else DEFAULT_RUNS_LOG_PATH

    seen_file = s_dir / "job-catcher-seen.json"
    queue_file = s_dir / "job-catcher-queue.jsonl"

    # Step 1: Catalog
    if boards is None:
        boards = load_catalog(c_path, secondary_catalog_path)

    # Step 2: Check baseline seed condition (+ corrupt seen-file guard)
    seen_exists = seen_file.is_file()
    loaded_seen = load_seen(seen_file)
    seen_corrupt = seen_exists and loaded_seen is None
    if seen_corrupt:
        # Never treat a corrupt seen file as empty: back it up and re-seed as a
        # baseline (queue nothing) instead of re-triaging the whole catalog.
        backup = seen_file.with_name(f"job-catcher-seen.corrupt-{int(time.time())}.json")
        seen_file.rename(backup)
        logger.warning("Corrupt seen file backed up to %s; re-seeding as baseline.", backup)
        seen_ids: Set[str] = set()
    else:
        seen_ids = loaded_seen if loaded_seen is not None else set()
    is_baseline = ((not seen_exists) or seen_corrupt) and (not no_baseline)

    # Step 3: Fetch all boards with error isolation and polite delay
    boards_ok = 0
    boards_failed = 0
    all_postings: List[Posting] = []

    fetcher = fetch_board_fn or (lambda b: fetch_board(b, timeout=20.0))

    for idx, board in enumerate(boards):
        if idx > 0 and polite_delay > 0:
            time.sleep(polite_delay)

        try:
            result = fetcher(board)
            if result.is_success:
                boards_ok += 1
                all_postings.extend(result.postings)
            else:
                boards_failed += 1
                logger.warning("Board failed: %s [%s:%s]: %s", board.company, board.platform, board.slug, result.error)
        except Exception as e:
            # Absolute safety net: never raise out of cycle
            boards_failed += 1
            logger.error("Unexpected board error for %s [%s:%s]: %s", board.company, board.platform, board.slug, e)

    # Deduplicate postings seen in this batch by composite key (platform:slug:job_id)
    unique_postings: List[Posting] = []
    batch_ids: Set[str] = set()
    for p in all_postings:
        key = posting_key(p)
        if p.job_id and key not in batch_ids:
            batch_ids.add(key)
            unique_postings.append(p)

    postings_seen_count = len(unique_postings)

    if is_baseline:
        # BASELINE SEED: write all current postings to seen-list, queue NOTHING
        updated_seen = seen_ids | batch_ids
        save_seen(seen_file, updated_seen)

        duration = time.time() - start_time
        log_entry = make_run_log_record(
            cycle_time=cycle_time,
            boards_ok=boards_ok,
            boards_failed=boards_failed,
            postings_seen=postings_seen_count,
            postings_new=0,
            postings_queued=0,
            duration_seconds=duration,
        )
        append_run_log(r_path, log_entry)

        return CycleResult(
            boards_ok=boards_ok,
            boards_failed=boards_failed,
            postings_seen=postings_seen_count,
            postings_new=0,
            postings_queued=0,
            baseline_run=True,
            duration_seconds=duration,
        )

    # Step 4: Diff against seen-list
    new_postings = [p for p in unique_postings if posting_key(p) not in seen_ids]
    postings_new_count = len(new_postings)

    # Step 5: Deterministic filter
    filter_survivors: List[tuple[Posting, FilterResult]] = []
    for p in new_postings:
        f_res = filter_posting(p)
        if f_res.passed:
            filter_survivors.append((p, f_res))

    # Step 6: LLM triage on filter survivors
    postings_queued_count = 0
    for p, f_res in filter_survivors:
        t_res = triage_posting(p, client=triage_client)
        if t_res.kept:
            queue_record = make_queue_record(p, f_res, t_res)
            append_to_queue(queue_file, queue_record)
            postings_queued_count += 1

    # Step 7: Record every seen posting (kept or killed) in seen-list
    updated_seen = seen_ids | batch_ids
    save_seen(seen_file, updated_seen)

    duration = time.time() - start_time
    # Step 8: Per-cycle run log
    log_entry = make_run_log_record(
        cycle_time=cycle_time,
        boards_ok=boards_ok,
        boards_failed=boards_failed,
        postings_seen=postings_seen_count,
        postings_new=postings_new_count,
        postings_queued=postings_queued_count,
        duration_seconds=duration,
    )
    append_run_log(r_path, log_entry)

    return CycleResult(
        boards_ok=boards_ok,
        boards_failed=boards_failed,
        postings_seen=postings_seen_count,
        postings_new=postings_new_count,
        postings_queued=postings_queued_count,
        baseline_run=False,
        duration_seconds=duration,
    )
