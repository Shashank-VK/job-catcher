# Job-Catcher

Job-Catcher is a lightweight, single-purpose Python service that polls the public ATS JSON feeds (Greenhouse, Ashby, Lever) for companies in the watchlist catalog, diffs against a persistent seen-list, runs deterministic fresher filtering followed by local LLM triage via OmniRoute, and appends survivors to a downstream queue file.

---

## The No-Certification Boundary

> [!IMPORTANT]
> **Strict Operational Boundary**: Job-Catcher NEVER certifies candidates, NEVER verifies pay, and NEVER applies to jobs.
> Downstream gates (C1 / C11) remain entirely unchanged. Job-Catcher is purely an ATS-level surfacing and triage watcher.

---

## System Architecture & Workflow

1. **Catalog Load**: Reads `watchlist_sources.json` (and optional `xobin_sources.json` if present) into structured `Board(company, platform, slug)` instances, deduplicated.
2. **Fetch**: Polls public endpoints via `urllib` (timeout 20s, polite 0.3s delay between boards):
   - **Greenhouse**: `https://boards-api.greenhouse.io/v1/boards/{slug}/jobs`
   - **Ashby**: `https://api.ashbyhq.com/posting-api/job-board/{slug}?includeCompensation=true`
   - **Lever**: `https://api.lever.co/v0/postings/{slug}?mode=json`
   *Per-board failures are isolated as error records and never abort the cycle.*
3. **Diff & Baseline Seed**:
   - First run seeds all active postings into the seen-list and queues **nothing** (unless overridden by `--no-baseline`).
   - Subsequent cycles diff incoming jobs against `job-catcher-seen.json` (atomic write via temp file + `os.replace`).
4. **Deterministic Fresher Filter**:
   - Drops explicit seniority titles (`senior`, `staff`, `principal`, `lead`, `manager`, `director`).
   - Drops explicit experience requirements >= 3 years (`3+ years`, etc.).
   - Drops explicit "no freshers" or non-target batch exclusions.
   - Pass-through on missing signals (never kills on absence of a signal).
5. **OmniRoute LLM Triage**:
   - Calls `http://localhost:20128/v1/chat/completions` using model `gemini/gemini-3.1-flash-lite`.
   - API key loaded dynamically from `~/.config/omniroute-local/client_key` (never printed/logged).
   - Strict JSON output parsing.
   - **Graceful degradation**: if OmniRoute is unreachable, errors, or times out, the posting is KEPT with verdict `triage_unavailable`.
6. **Queue & Logging**:
   - Kept postings appended as JSON lines to `job-catcher-queue.jsonl`.
   - Cycle statistics appended to `job-catcher-runs.jsonl`.

---

## State & Queue File Locations

- **Seen List**: `~/workspace/goals/land-a-ds-ml-internship-or-job/hidden_files/job-catcher-seen.json`
- **Queue File**: `~/workspace/goals/land-a-ds-ml-internship-or-job/hidden_files/job-catcher-queue.jsonl`
- **Run Log**: `./job-catcher-runs.jsonl` (in project directory)

---

## Run Modes

### 1. Single Run (`--once`)
Runs one poll cycle and exits `0`, even if individual boards fail or return HTTP 404:
```bash
python3 run_catcher.py --once
```

### 2. Continuous Loop (`--loop`)
Runs on a recurring interval (default 600 seconds = 10 minutes):
```bash
python3 run_catcher.py --loop --interval 600
```

### 3. CLI Options
- `--catalog PATH`: Custom path to watchlist JSON.
- `--state-dir PATH`: Custom directory for seen-list and queue file.
- `--no-baseline`: Disable first-run baseline seed; treats all current postings as new.
- `--delay SECONDS`: Delay between board fetches (default: 0.3s).

---

## Loop Setup

**Deployed setup on this VM (2026-10-23):** the systemd user bus is not reachable here,
so the loop runs as a detached process supervised by a daily cron liveness check:

```bash
cd ~/workspace/goals/land-a-ds-ml-internship-or-job/builds/job-catcher
setsid nohup .venv/bin/python run_catcher.py --loop --interval 600 >> job-catcher-loop.log 2>&1 &
echo $! > .builder-os/loop.pid
```

The daily cron check verifies the PID is alive and the newest run-log line is fresh;
if the loop is dead it relaunches it the same way and reports. After a VM restart the
loop does not auto-start — the cron check (or any operator) relaunches it; the seen-list
on disk makes a relaunch safe (no re-queue flood; a missing/corrupt seen file re-seeds
as a baseline instead).

**Alternative — systemd user service** (on a machine with a working user bus):

1. Create `~/.config/systemd/user/job-catcher.service`:

```ini
[Unit]
Description=Job-Catcher ATS Watcher Service
After=network.target

[Service]
Type=simple
WorkingDirectory=%h/workspace/goals/land-a-ds-ml-internship-or-job/builds/job-catcher
ExecStart=%h/workspace/goals/land-a-ds-ml-internship-or-job/builds/job-catcher/.venv/bin/python run_catcher.py --loop --interval 600
Restart=always
RestartSec=30
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=default.target
```

2. Reload daemon and start service:
```bash
systemctl --user daemon-reload
systemctl --user enable --now job-catcher.service
```

3. Check status and logs:
```bash
systemctl --user status job-catcher.service
journalctl --user -u job-catcher.service -f
```

---

## Honest Limitations

- **ATS Feeds Only**: Targets Greenhouse, Ashby, and Lever JSON endpoints only. It does NOT scrape aggregators like Naukri, LinkedIn, or Google Jobs.
- **Local Model Dependency**: Relies on a local OmniRoute proxy on port 20128. If OmniRoute is down, the fail-safe keeps postings marked as `triage_unavailable` rather than dropping them.
- **Slug Validity**: ATS slugs in candidate lists may return HTTP 404 if companies change platforms or slug names; these are logged as errors without breaking execution.
