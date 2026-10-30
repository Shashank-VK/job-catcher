#!/usr/bin/env python3
"""BUILDER-OS verify-gate smoke: a full catcher cycle against fixture data.

Two fake Greenhouse boards return the SAME job_id (the FCAR collision case).
Cycle 1 must baseline-seed both postings and queue nothing; cycle 2 adds one
posting on one board and must queue exactly that one. Exits 0 on success.
"""
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from jobcatcher.catalog import Board
from jobcatcher.fetch import FetchResult, Posting
from jobcatcher.run import run_cycle
from jobcatcher.triage import OmniRouteClient, TriageResult


class KeepAll(OmniRouteClient):
    def __init__(self):
        pass

    def triage(self, posting):
        return TriageResult(verdict="KEEP", kept=True, role_family="SWE", reason="smoke")


def posting(slug, job_id, title="Software Engineer"):
    return Posting(company=slug.title(), platform="greenhouse", slug=slug,
                   job_id=job_id, title=title, url=f"http://x/{slug}/{job_id}")


def main() -> int:
    with tempfile.TemporaryDirectory() as td:
        state = Path(td) / "state"; state.mkdir()
        runs = Path(td) / "runs.jsonl"
        boards = [Board(company="A", platform="greenhouse", slug="alpha"),
                  Board(company="B", platform="greenhouse", slug="beta")]

        r1 = run_cycle(state_dir=state, runs_log_path=runs, boards=boards,
                       fetch_board_fn=lambda b: FetchResult(board=b, postings=[posting(b.slug, "100")]),
                       polite_delay=0.0)
        assert r1.baseline_run and r1.postings_seen == 2 and r1.postings_queued == 0, r1

        def v2(b):
            if b.slug == "beta":
                return FetchResult(board=b, postings=[posting("beta", "100"),
                                                      posting("beta", "101", "Backend Engineer Intern")])
            return FetchResult(board=b, postings=[posting("alpha", "100")])

        r2 = run_cycle(state_dir=state, runs_log_path=runs, boards=boards,
                       fetch_board_fn=v2, polite_delay=0.0, triage_client=KeepAll())
        assert r2.postings_new == 1 and r2.postings_queued == 1, r2
        q = (state / "job-catcher-queue.jsonl").read_text().splitlines()
        assert len(q) == 1 and json.loads(q[0])["job_id"] == "101"
    print("SMOKE OK: baseline seeded 2 colliding-id postings, cycle 2 queued exactly the 1 new posting")
    return 0


if __name__ == "__main__":
    sys.exit(main())
