"""Tests for poll loop and once mode (catch-007)."""

import inspect
import json
from pathlib import Path
import pytest

from jobcatcher.catalog import Board
from jobcatcher.fetch import FetchResult, Posting
import run_catcher


def test_cli_once_with_fakes_exits_zero(tmp_path: Path, monkeypatch):
    """catch-007: Unit/CLI: --once with fakes exits 0."""
    catalog_path = tmp_path / "watchlist_sources.json"
    catalog_path.write_text(
        json.dumps({
            "companies": [
                {"name": "Stripe", "greenhouse": [{"slug": "stripe"}]},
            ]
        }),
        encoding="utf-8",
    )
    state_dir = tmp_path / "hidden_files"
    state_dir.mkdir()

    # Fake fetcher to avoid network calls
    def fake_fetch_board(board, timeout=20.0):
        return FetchResult(
            board=board,
            postings=[
                Posting(
                    company="Stripe",
                    platform="greenhouse",
                    slug="stripe",
                    job_id="stripe-1",
                    title="Software Engineer",
                    url="https://example.com/1",
                )
            ],
            is_success=True,
        )

    monkeypatch.setattr("jobcatcher.run.fetch_board", fake_fetch_board)

    # Invoke run_catcher.main with --once
    exit_code = run_catcher.main([
        "--once",
        "--catalog", str(catalog_path),
        "--state-dir", str(state_dir),
        "--runs-log", str(tmp_path / "runs.jsonl"),
        "--delay", "0.0",
    ])

    assert exit_code == 0
    # Baseline seed created seen file
    assert (state_dir / "job-catcher-seen.json").is_file()


def test_cli_once_exits_zero_even_when_boards_fail(tmp_path: Path, monkeypatch):
    """Verify --once exits 0 even when individual boards fail."""
    catalog_path = tmp_path / "watchlist_sources.json"
    catalog_path.write_text(
        json.dumps({
            "companies": [
                {"name": "FailingCo", "greenhouse": [{"slug": "failing"}]},
            ]
        }),
        encoding="utf-8",
    )
    state_dir = tmp_path / "hidden_files"
    state_dir.mkdir()

    # Fake fetcher returns failure
    def fake_failing_board(board, timeout=20.0):
        return FetchResult(
            board=board,
            postings=[],
            error="HTTP 404: Not Found",
            status_code=404,
            is_success=False,
        )

    monkeypatch.setattr("jobcatcher.run.fetch_board", fake_failing_board)

    exit_code = run_catcher.main([
        "--once",
        "--catalog", str(catalog_path),
        "--state-dir", str(state_dir),
        "--runs-log", str(tmp_path / "runs.jsonl"),
        "--delay", "0.0",
    ])

    assert exit_code == 0


def test_code_inspection_loop_wraps_in_try_except_and_sleeps():
    """catch-007: Code inspection: loop wraps cycles in try/except and sleeps the interval."""
    source = inspect.getsource(run_catcher.main)
    # Check that there is a while loop
    assert "while True:" in source
    # Check that loop wraps run_cycle in try/except
    assert "try:" in source
    assert "run_cycle(" in source
    assert "except Exception as e:" in source or "except Exception" in source
    # Check that time.sleep is called with interval
    assert "time.sleep(args.interval)" in source
