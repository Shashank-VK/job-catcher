"""Tests for queue writer and run log (catch-006)."""

import json
from pathlib import Path
import pytest

from jobcatcher.catalog import Board
from jobcatcher.fetch import FetchResult, Posting
from jobcatcher.filter import FilterResult
from jobcatcher.queue import (
    IST_TZ,
    append_run_log,
    append_to_queue,
    make_queue_record,
    make_run_log_record,
    now_ist_iso,
)
from jobcatcher.run import run_cycle
from jobcatcher.triage import OmniRouteClient, TriageResult


def test_ist_timestamp_format():
    """Verify ISO IST timestamp has +05:30 offset."""
    ts = now_ist_iso()
    assert "+05:30" in ts


def test_queue_and_run_log_records_schema():
    """Verify structure and fields of queue and run log records."""
    p = Posting(
        company="Razorpay",
        platform="greenhouse",
        slug="razorpay",
        job_id="rzp-999",
        title="Software Engineer - Fresh Graduate",
        url="https://razorpay.com/jobs/999",
        location="Bengaluru",
        posted_at="2026-10-23T05:00:00Z",
        compensation=None,
        description_text="Entry level SWE opening.",
    )
    f_res = FilterResult(passed=True)
    t_res = TriageResult(
        verdict="KEEP",
        kept=True,
        role_family="SWE",
        location_remote="Bengaluru",
        batch_eligibility="2026/2027",
        pay_signal="not specified",
        reason="Entry-level match",
    )

    q_rec = make_queue_record(p, f_res, t_res)
    assert q_rec["company"] == "Razorpay"
    assert q_rec["platform"] == "greenhouse"
    assert q_rec["source_platform"] == "greenhouse"
    assert q_rec["job_id"] == "rzp-999"
    assert q_rec["title"] == "Software Engineer - Fresh Graduate"
    assert q_rec["url"] == "https://razorpay.com/jobs/999"
    assert q_rec["location"] == "Bengaluru"
    assert "+05:30" in q_rec["fetched_at"]
    assert q_rec["filter_result"]["passed"] is True
    assert q_rec["triage_verdict"] == "KEEP"
    assert q_rec["extracted_signals"]["role_family"] == "SWE"

    r_rec = make_run_log_record(
        cycle_time=q_rec["fetched_at"],
        boards_ok=10,
        boards_failed=2,
        postings_seen=40,
        postings_new=5,
        postings_queued=3,
        duration_seconds=1.23,
    )
    assert r_rec["boards_ok"] == 10
    assert r_rec["boards_failed"] == 2
    assert r_rec["postings_seen"] == 40
    assert r_rec["postings_new"] == 5
    assert r_rec["postings_queued"] == 3
    assert r_rec["duration_seconds"] == 1.23


def test_faked_fetch_filter_triage_cycle_integration(tmp_path: Path):
    """
    catch-006:
    Integration: faked fetch+filter+triage cycle -> queue lines match schema incl. fetched_at + verdict.
    Integration: run log line counts match the cycle.
    """
    state_dir = tmp_path / "hidden_files"
    state_dir.mkdir()
    runs_log = tmp_path / "job-catcher-runs.jsonl"
    seen_file = state_dir / "job-catcher-seen.json"
    queue_file = state_dir / "job-catcher-queue.jsonl"

    # Pre-seed seen-list with an existing job so this is NOT a baseline run
    seen_file.write_text(json.dumps(["existing-job-1"]), encoding="utf-8")

    # Postings returned by fake fetch
    p_pass_keep = Posting(
        company="Stripe",
        platform="greenhouse",
        slug="stripe",
        job_id="job-new-1",
        title="Software Engineer, Backend",
        url="https://stripe.com/job/new-1",
        location="Bengaluru",
        description_text="Great opening for early career backend engineers.",
    )
    p_filter_kill = Posting(
        company="Stripe",
        platform="greenhouse",
        slug="stripe",
        job_id="job-new-2",
        title="Senior Director of Engineering",
        url="https://stripe.com/job/new-2",
        location="Remote",
        description_text="Lead the org.",
    )
    p_triage_kill = Posting(
        company="Stripe",
        platform="greenhouse",
        slug="stripe",
        job_id="job-new-3",
        title="Account Executive",
        url="https://stripe.com/job/new-3",
        location="Dublin",
        description_text="Enterprise sales.",
    )

    board = Board(company="Stripe", platform="greenhouse", slug="stripe")

    def fake_fetcher(b: Board) -> FetchResult:
        return FetchResult(
            board=b,
            postings=[p_pass_keep, p_filter_kill, p_triage_kill],
            is_success=True,
        )

    class MockClient(OmniRouteClient):
        def triage(self, posting: Posting) -> TriageResult:
            if "Software Engineer" in posting.title:
                return TriageResult(
                    verdict="KEEP",
                    kept=True,
                    role_family="SWE",
                    location_remote=posting.location,
                    batch_eligibility="2026/2027 eligible",
                    pay_signal="Market rate",
                    reason="Target SWE entry role",
                )
            return TriageResult(
                verdict="KILL",
                kept=False,
                role_family="Sales",
                reason="Non-SWE role",
            )

    result = run_cycle(
        state_dir=state_dir,
        runs_log_path=runs_log,
        boards=[board],
        fetch_board_fn=fake_fetcher,
        triage_client=MockClient(),
        polite_delay=0.0,
    )

    # Check result counts
    assert result.boards_ok == 1
    assert result.boards_failed == 0
    assert result.postings_seen == 3
    assert result.postings_new == 3
    assert result.postings_queued == 1

    # Verify queue file schema and contents
    assert queue_file.is_file()
    queue_lines = [json.loads(line) for line in queue_file.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(queue_lines) == 1
    q_entry = queue_lines[0]

    assert q_entry["job_id"] == "job-new-1"
    assert q_entry["company"] == "Stripe"
    assert q_entry["title"] == "Software Engineer, Backend"
    assert q_entry["url"] == "https://stripe.com/job/new-1"
    assert q_entry["location"] == "Bengaluru"
    assert "+05:30" in q_entry["fetched_at"]
    assert q_entry["filter_result"]["passed"] is True
    assert q_entry["triage_verdict"] == "KEEP"
    assert q_entry["extracted_signals"]["role_family"] == "SWE"

    # Verify run log line counts match the cycle
    assert runs_log.is_file()
    run_lines = [json.loads(line) for line in runs_log.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(run_lines) == 1
    r_entry = run_lines[0]
    assert r_entry["boards_ok"] == 1
    assert r_entry["boards_failed"] == 0
    assert r_entry["postings_seen"] == 3
    assert r_entry["postings_new"] == 3
    assert r_entry["postings_queued"] == 1
    assert "+05:30" in r_entry["cycle_time"]
