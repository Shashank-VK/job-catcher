"""Queue writer and run log writer for job-catcher."""

import datetime as dt
import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional

from .fetch import Posting
from .filter import FilterResult
from .triage import TriageResult

logger = logging.getLogger(__name__)

# Indian Standard Time timezone (+05:30)
IST_TZ = dt.timezone(dt.timedelta(hours=5, minutes=30))


def now_ist_iso() -> str:
    """Return current timestamp in ISO 8601 with IST offset."""
    return dt.datetime.now(IST_TZ).isoformat()


def make_queue_record(
    posting: Posting,
    filter_result: FilterResult,
    triage_result: TriageResult,
    fetched_at_ist: Optional[str] = None,
) -> Dict[str, Any]:
    """Construct queue record matching specs.md Section 6."""
    fetched_at = fetched_at_ist or now_ist_iso()
    return {
        "platform": posting.platform,
        "source_platform": posting.platform,
        "company": posting.company,
        "slug": posting.slug,
        "job_id": posting.job_id,
        "title": posting.title,
        "url": posting.url,
        "location": posting.location,
        "posted_at": posting.posted_at,
        "compensation": posting.compensation,
        "fetched_at": fetched_at,
        "filter_result": {
            "passed": filter_result.passed,
            "reason": filter_result.reason,
        },
        "triage_verdict": triage_result.verdict,
        "extracted_signals": {
            "role_family": triage_result.role_family,
            "location_remote": triage_result.location_remote,
            "batch_eligibility": triage_result.batch_eligibility,
            "pay_signal": triage_result.pay_signal,
            "reason": triage_result.reason,
        },
        "role_family": triage_result.role_family,
        "location_remote": triage_result.location_remote,
        "batch_eligibility": triage_result.batch_eligibility,
        "pay_signal": triage_result.pay_signal,
    }


def make_run_log_record(
    cycle_time: str,
    boards_ok: int,
    boards_failed: int,
    postings_seen: int,
    postings_new: int,
    postings_queued: int,
    duration_seconds: float = 0.0,
) -> Dict[str, Any]:
    """Construct run log record matching specs.md Section 8."""
    return {
        "cycle_time": cycle_time,
        "timestamp": cycle_time,
        "boards_ok": boards_ok,
        "boards_failed": boards_failed,
        "postings_seen": postings_seen,
        "postings_new": postings_new,
        "postings_queued": postings_queued,
        "duration_seconds": round(duration_seconds, 2),
    }


def append_to_queue(queue_path: str | Path, record: Dict[str, Any]) -> None:
    """Append a single record as a JSON line to the queue file."""
    p = Path(queue_path).resolve()
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def append_run_log(run_log_path: str | Path, record: Dict[str, Any]) -> None:
    """Append a cycle run record as a JSON line to the runs log file."""
    p = Path(run_log_path).resolve()
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
