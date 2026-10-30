"""Tests for state diff and baseline seeding (catch-003)."""

from pathlib import Path
import pytest

from jobcatcher.catalog import Board
from jobcatcher.fetch import FetchResult, Posting
from jobcatcher.run import run_cycle
from jobcatcher.state import load_seen, save_seen
from jobcatcher.triage import OmniRouteClient, TriageResult


def test_atomic_save_and_load_seen(tmp_path: Path):
    """Test load_seen and save_seen with atomic file replacement."""
    seen_file = tmp_path / "test-seen.json"
    assert load_seen(seen_file) == set()

    ids = {"job-101", "job-102", "job-103"}
    save_seen(seen_file, ids)

    loaded = load_seen(seen_file)
    assert loaded == ids

    # Overwrite atomically with additional id
    ids.add("job-104")
    save_seen(seen_file, ids)
    assert load_seen(seen_file) == ids


def test_baseline_run_queues_zero_and_writes_all_ids(tmp_path: Path):
    """catch-003: Unit: baseline run queues 0 and writes all ids."""
    state_dir = tmp_path / "hidden_files"
    state_dir.mkdir()
    runs_log = tmp_path / "runs.jsonl"
    seen_file = state_dir / "job-catcher-seen.json"
    queue_file = state_dir / "job-catcher-queue.jsonl"

    p1 = Posting(company="CoA", platform="greenhouse", slug="coa", job_id="id-1", title="Software Engineer", url="http://x/1")
    p2 = Posting(company="CoB", platform="ashby", slug="cob", job_id="id-2", title="Data Scientist", url="http://x/2")

    board1 = Board(company="CoA", platform="greenhouse", slug="coa")
    board2 = Board(company="CoB", platform="ashby", slug="cob")

    def fake_fetcher(board: Board) -> FetchResult:
        if board.slug == "coa":
            return FetchResult(board=board, postings=[p1])
        return FetchResult(board=board, postings=[p2])

    result = run_cycle(
        state_dir=state_dir,
        runs_log_path=runs_log,
        boards=[board1, board2],
        fetch_board_fn=fake_fetcher,
        polite_delay=0.0,
    )

    assert result.baseline_run is True
    assert result.postings_seen == 2
    assert result.postings_new == 0
    assert result.postings_queued == 0

    # Ensure queue file does not exist or is empty
    if queue_file.exists():
        assert queue_file.read_text(encoding="utf-8").strip() == ""

    # Ensure seen-list contains all ids
    saved_seen = load_seen(seen_file)
    assert saved_seen == {"greenhouse:coa:id-1", "ashby:cob:id-2"}


def test_second_run_with_one_added_posting_queues_exactly_that_one(tmp_path: Path):
    """catch-003: Unit: second run with one added posting queues exactly that one."""
    state_dir = tmp_path / "hidden_files"
    state_dir.mkdir()
    runs_log = tmp_path / "runs.jsonl"
    seen_file = state_dir / "job-catcher-seen.json"
    queue_file = state_dir / "job-catcher-queue.jsonl"

    p1 = Posting(company="CoA", platform="greenhouse", slug="coa", job_id="id-1", title="Software Engineer", url="http://x/1")
    p2 = Posting(company="CoB", platform="ashby", slug="cob", job_id="id-2", title="Data Scientist", url="http://x/2")
    p3 = Posting(company="CoC", platform="lever", slug="coc", job_id="id-3", title="Backend Engineer Intern", url="http://x/3")

    board1 = Board(company="CoA", platform="greenhouse", slug="coa")
    board2 = Board(company="CoB", platform="ashby", slug="cob")
    board3 = Board(company="CoC", platform="lever", slug="coc")

    # Step 1: Baseline run with id-1 and id-2
    def fetcher_cycle1(board: Board) -> FetchResult:
        if board.slug == "coa":
            return FetchResult(board=board, postings=[p1])
        return FetchResult(board=board, postings=[p2])

    res1 = run_cycle(
        state_dir=state_dir,
        runs_log_path=runs_log,
        boards=[board1, board2],
        fetch_board_fn=fetcher_cycle1,
        polite_delay=0.0,
    )
    assert res1.baseline_run is True
    assert res1.postings_queued == 0
    assert load_seen(seen_file) == {"greenhouse:coa:id-1", "ashby:cob:id-2"}

    # Mock triage client that keeps p3
    class MockTriageClient(OmniRouteClient):
        def triage(self, posting: Posting) -> TriageResult:
            return TriageResult(
                verdict="KEEP",
                kept=True,
                role_family="SWE",
                reason="Intern signal",
            )

    # Step 2: Second run adds p3 (now id-1, id-2, and id-3 are returned)
    def fetcher_cycle2(board: Board) -> FetchResult:
        if board.slug == "coa":
            return FetchResult(board=board, postings=[p1])
        elif board.slug == "cob":
            return FetchResult(board=board, postings=[p2])
        return FetchResult(board=board, postings=[p3])

    res2 = run_cycle(
        state_dir=state_dir,
        runs_log_path=runs_log,
        boards=[board1, board2, board3],
        fetch_board_fn=fetcher_cycle2,
        polite_delay=0.0,
        triage_client=MockTriageClient(),
    )

    assert res2.baseline_run is False
    assert res2.postings_seen == 3
    assert res2.postings_new == 1
    assert res2.postings_queued == 1

    # Check queue file has exactly 1 entry for id-3
    assert queue_file.is_file()
    lines = [line.strip() for line in queue_file.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(lines) == 1
    import json
    queued_item = json.loads(lines[0])
    assert queued_item["job_id"] == "id-3"
    assert queued_item["title"] == "Backend Engineer Intern"

    # Seen list now includes all 3
    assert load_seen(seen_file) == {"greenhouse:coa:id-1", "ashby:cob:id-2", "lever:coc:id-3"}
