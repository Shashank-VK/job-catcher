#!/usr/bin/env bash
# init.sh — BUILDER-OS bootstrap + verify gate for job-catcher.
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${PROJECT_ROOT:-$(dirname "$ROOT_DIR")}"
cd "$PROJECT_ROOT"
VERIFY_CMD=".venv/bin/python -m pytest -q"
START_CMD=".venv/bin/python run_catcher.py --loop --interval 600"
echo "== verify =="; $VERIFY_CMD
echo "== smoke (fixture cycle) =="; .venv/bin/python .builder-os/smoke_fixture.py
echo "INIT OK"
