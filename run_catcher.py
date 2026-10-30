#!/usr/bin/env python3
"""CLI entry point for job-catcher."""

import argparse
import logging
from pathlib import Path
import sys
import time

from jobcatcher.run import (
    DEFAULT_CATALOG_PATH,
    DEFAULT_STATE_DIR,
    run_cycle,
)

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("run_catcher")


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Job-Catcher: ATS feed watcher and triager."
    )
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument(
        "--once",
        action="store_true",
        default=True,
        help="Run a single poll cycle and exit 0 (default mode).",
    )
    mode_group.add_argument(
        "--loop",
        action="store_true",
        help="Run continuously in a loop.",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=600,
        help="Polling interval in seconds for loop mode (default: 600).",
    )
    parser.add_argument(
        "--catalog",
        type=str,
        default=str(DEFAULT_CATALOG_PATH),
        help="Path to watchlist_sources.json.",
    )
    parser.add_argument(
        "--state-dir",
        type=str,
        default=str(DEFAULT_STATE_DIR),
        help="Directory where seen list and queue files reside.",
    )
    parser.add_argument(
        "--runs-log",
        type=str,
        default=None,
        help="Path to the per-cycle run log (default: job-catcher-runs.jsonl in the project dir).",
    )
    parser.add_argument(
        "--no-baseline",
        action="store_true",
        help="Disable baseline seed on first run (treat all postings as new).",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=0.3,
        help="Polite delay between board fetches in seconds (default: 0.3).",
    )

    args = parser.parse_args(argv)
    if args.loop:
        args.once = False
    return args


def main(argv=None):
    args = parse_args(argv)

    catalog_path = Path(args.catalog)
    state_dir = Path(args.state_dir)

    logger.info(
        "Starting job-catcher (mode=%s, catalog=%s, state_dir=%s)",
        "loop" if args.loop else "once",
        catalog_path,
        state_dir,
    )

    if args.loop:
        while True:
            try:
                result = run_cycle(
                    catalog_path=catalog_path,
                    state_dir=state_dir,
                    runs_log_path=Path(args.runs_log) if args.runs_log else None,
                    no_baseline=args.no_baseline,
                    polite_delay=args.delay,
                )
                logger.info(
                    "Cycle finished: ok=%d failed=%d seen=%d new=%d queued=%d (baseline=%s)",
                    result.boards_ok,
                    result.boards_failed,
                    result.postings_seen,
                    result.postings_new,
                    result.postings_queued,
                    result.baseline_run,
                )
            except Exception as e:
                # Per-cycle error survival in loop
                logger.error("Unhandled error during poll cycle: %s", e, exc_info=True)

            try:
                time.sleep(args.interval)
            except KeyboardInterrupt:
                logger.info("Loop interrupted by user. Exiting cleanly.")
                break
        return 0

    # Once mode: always exit 0
    try:
        result = run_cycle(
            catalog_path=catalog_path,
            state_dir=state_dir,
            runs_log_path=Path(args.runs_log) if args.runs_log else None,
            no_baseline=args.no_baseline,
            polite_delay=args.delay,
        )
        logger.info(
            "Cycle finished: ok=%d failed=%d seen=%d new=%d queued=%d (baseline=%s)",
            result.boards_ok,
            result.boards_failed,
            result.postings_seen,
            result.postings_new,
            result.postings_queued,
            result.baseline_run,
        )
    except Exception as e:
        logger.error("Run cycle error: %s", e, exc_info=True)

    return 0


if __name__ == "__main__":
    sys.exit(main())
