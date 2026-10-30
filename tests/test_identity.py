"""Regression tests for the FCAR composite-identity defect + corrupt-seen guard.

FCAR (2026-10-23) proved that keying the seen-list on the bare job_id silently
dropped postings when two boards returned the same numeric id. Identity is now
platform:slug:job_id everywhere (dedupe, diff, seen-list).
"""

import json
from pathlib import Path

from jobcatcher.catalog import Board
from jobcatcher.fetch import FetchResult, Posting
from jobcatcher.run import run_cycle
from jobcatcher.state import load_seen
from jobcatcher.triage import OmniRouteClient, TriageResult


class KeepAll(OmniRouteClient):
    def __init__(self):
        pass

    def triage(self, posting: Posting) -> TriageResult:
        return TriageResult(verdict="KEEP", kept=True, role_family="SWE", reason="test")


def _posting(slug: str, job_id: str, title: str = "Software Engineer") -> Posting:
    return Posting(company=slug.title(), platform="greenhouse", slug=slug,
                   job_id=job_id, title=title, url=f"http://x/{slug}/{job_id}")


def test_colliding_job_ids_across_boards_are_never_dropped(tmp_path: Path):
    state_dir = tmp_path / "state"; state_dir.mkdir()
    runs_log = tmp_path / "runs.jsonl"
    seen_file = state_dir / "job-catcher-seen.json"
    queue_file = state_dir / "job-catcher-queue.jsonl"

    board_a = Board(company="A", platform="greenhouse", slug="alpha")
    board_b = Board(company="B", platform="greenhouse", slug="beta")

    # Both boards return the SAME numeric job_id "100" — different postings.
    def fetch_v1(board: Board) -> FetchResult:
        return FetchResult(board=board, postings=[_posting(board.slug, "100")])

    res1 = run_cycle(state_dir=state_dir, runs_log_path=runs_log,
                     boards=[board_a, board_b], fetch_board_fn=fetch_v1,
                     polite_delay=0.0)
    assert res1.baseline_run is True
    assert res1.postings_seen == 2  # was 1 under the bare-id defect
    assert load_seen(seen_file) == {"greenhouse:alpha:100", "greenhouse:beta:100"}

    # Cycle 2: beta adds posting "101"; alpha unchanged. Exactly the new one queues.
    def fetch_v2(board: Board) -> FetchResult:
        if board.slug == "beta":
            return FetchResult(board=board, postings=[_posting("beta", "100"),
                                                      _posting("beta", "101", "Backend Engineer Intern")])
        return FetchResult(board=board, postings=[_posting("alpha", "100")])

    res2 = run_cycle(state_dir=state_dir, runs_log_path=runs_log,
                     boards=[board_a, board_b], fetch_board_fn=fetch_v2,
                     polite_delay=0.0, triage_client=KeepAll())
    assert res2.postings_new == 1
    assert res2.postings_queued == 1
    lines = [json.loads(l) for l in queue_file.read_text().splitlines() if l.strip()]
    assert len(lines) == 1 and lines[0]["job_id"] == "101" and lines[0]["slug"] == "beta"


def test_corrupt_seen_file_reseeds_as_baseline_without_flooding(tmp_path: Path):
    state_dir = tmp_path / "state"; state_dir.mkdir()
    runs_log = tmp_path / "runs.jsonl"
    seen_file = state_dir / "job-catcher-seen.json"
    queue_file = state_dir / "job-catcher-queue.jsonl"
    seen_file.write_text("{ this is not json", encoding="utf-8")

    board = Board(company="A", platform="greenhouse", slug="alpha")

    def fetch(board: Board) -> FetchResult:
        return FetchResult(board=board, postings=[_posting("alpha", "100")])

    res = run_cycle(state_dir=state_dir, runs_log_path=runs_log,
                    boards=[board], fetch_board_fn=fetch, polite_delay=0.0)
    assert res.baseline_run is True
    assert res.postings_queued == 0
    if queue_file.exists():
        assert queue_file.read_text().strip() == ""
    # Corrupt file preserved as a backup, fresh seen-list written with the composite key.
    backups = list(state_dir.glob("job-catcher-seen.corrupt-*.json"))
    assert len(backups) == 1
    assert load_seen(seen_file) == {"greenhouse:alpha:100"}


def test_scalar_seen_file_is_treated_as_corrupt(tmp_path: Path):
    """A seen file containing valid JSON of the wrong shape (e.g. `123`) must hit
    the corruption path (backup + baseline), not load as an empty set."""
    state_dir = tmp_path / "state"; state_dir.mkdir()
    runs_log = tmp_path / "runs.jsonl"
    seen_file = state_dir / "job-catcher-seen.json"
    seen_file.write_text("123", encoding="utf-8")

    board = Board(company="A", platform="greenhouse", slug="alpha")

    def fetch(board: Board) -> FetchResult:
        return FetchResult(board=board, postings=[_posting("alpha", "100")])

    res = run_cycle(state_dir=state_dir, runs_log_path=runs_log,
                    boards=[board], fetch_board_fn=fetch, polite_delay=0.0)
    assert res.baseline_run is True
    assert res.postings_queued == 0
    assert len(list(state_dir.glob("job-catcher-seen.corrupt-*.json"))) == 1
