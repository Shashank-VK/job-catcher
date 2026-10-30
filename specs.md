# specs.md — Job-Catcher v1 (BUILDER-OS locked specification)

## Overview
A small, single-purpose watcher that polls the public ATS JSON feeds of the companies in
C8's watchlist catalog, diffs against its own seen-list, runs a cheap triage on genuinely
new postings, and appends survivors to a queue file that C1/C11 consume. It NEVER certifies,
verifies pay, or applies — downstream gates are unchanged.

## Sources (catalog)
- Config of record: ~/workspace/goals/land-a-ds-ml-internship-or-job/hidden_files/watchlist_sources.json
  (126 companies; greenhouse/ashby/lever slug candidates, some unverified — a 404 from an
  unverified slug is data, logged, never a crash).
- The catalog loader also merges an optional second file in the same schema if present:
  hidden_files/xobin_sources.json (C8's Xobin wave list, when it lands as a file).
- Endpoints (all public, no auth):
  - Greenhouse: https://boards-api.greenhouse.io/v1/boards/{slug}/jobs
  - Ashby:      https://api.ashbyhq.com/posting-api/job-board/{slug}?includeCompensation=true
  - Lever:      https://api.lever.co/v0/postings/{slug}?mode=json

## Behaviour
1. One poll cycle: fetch every board in the catalog (sequential or small pool, polite
   per-request timeout 20s, one board's failure never aborts the cycle).
2. Normalize each posting to: company, platform, slug, job_id, title, url, location,
   posted_at (if given), compensation (Ashby, if given), description_text (plain text,
   truncated to 6000 chars, if the payload carries it cheaply).
3. Diff against the seen-list (job-catcher-seen.json, atomic writes). First ever run =
   BASELINE SEED: write all current postings to the seen-list, queue NOTHING
   (--no-baseline overrides).
4. Deterministic fresher filter on new postings (no LLM):
   - KILL only explicit exclusions: seniority words in the TITLE (senior, sr., staff,
     principal, lead, manager, director); experience demands of >=3 years in title or
     description in any of these explicit forms: "N+ years", an "X-Y years" / "X to Y
     years" range whose minimum is >=3, "at least / minimum / min. N years", or
     "N years (of) experience"; explicit "no freshers" / graduation-year exclusions
     other than 2026/2027/2028.
   - PASS-THROUGH everything else (the filter never kills on absence of a signal).
   (Amendment 2026-10-23 evening, throughput-plan order: v1's first catch-up cycle
   queued 6 items, all noise, because triage was down (degradation keeps) and the
   negative-only filter had three holes. The filter now also kills: (a) extended
   seniority/level markers in the title - vp, vice president, head, chief,
   architect, and level markers II/III, SDE-2/3, L2/L3 ("Head of AI Startups",
   "SDE - II" shipped in v1); (b) titles with NO role-family keyword - a positive
   gate over his verified families (engineer/developer/software/data/ML/AI/QA/
   SDET/scientist/analyst/test/platform et al.), which stops marketing, comms,
   creative, people-team and assistant roles ("Marketing internship",
   "Executive Assistant", "Intern - Creative & Communications" shipped in v1);
   (c) postings whose location is explicitly foreign with no India signal
   ("Remote - Ireland", EMEA city lists, NYC shipped in v1). Unstated location
   and country-less "Remote" still pass; C1 remains the eligibility authority -
   these gates cut obvious queue noise only, they do not certify.)
   (Amended 2026-10-23 after FCAR: the original text named only the "N+ years" form;
   the implementation's wider set of explicit >=3-year demand forms matches the
   feature list's ">=3 years demands" wording and the kill-explicit-exclusions intent.
   Spec and code now agree, and the filter tests pin every form.)
5. LLM triage (OmniRoute, Hermes pattern) on filter survivors:
   - POST http://localhost:20128/v1/chat/completions, model "gemini/gemini-3.1-flash-lite",
     API key read from ~/.config/omniroute-local/client_key (never printed/logged).
   - Prompt extracts: role family, location/remote signal, batch/2027 eligibility signal,
     pay signal. Verdict KEEP only with an intern/trainee/2027 signal OR an entry-level
     family match (SWE/backend/full-stack/data/ML/AI/QA); otherwise KILL.
   - GRACEFUL DEGRADATION: if OmniRoute is unreachable/errors/times out, the posting is
     KEPT with triage_verdict "triage_unavailable" — the catcher never silently drops.
6. Survivors are appended as JSON lines to hidden_files/job-catcher-queue.jsonl with:
   source platform, company, title, url, location, fetched_at (ISO IST), filter result,
   triage verdict + extracted signals.
7. Every seen posting (kept or killed) is recorded in the seen-list so nothing re-triages.
8. A per-cycle run log line is appended to job-catcher-runs.jsonl in the project dir:
   cycle time, boards ok/failed, postings seen/new/queued.

## Modes
- `python3 run_catcher.py --once` — one cycle, exit 0 even if individual boards fail.
- `python3 run_catcher.py --loop --interval 600` — supervised loop (systemd service).
- `--catalog PATH`, `--state-dir PATH` overrides for tests.

## Non-goals (No-Gos)
- No certification, no pay verification, no applying, no browser, no login anywhere.
- No Naukri/Google Jobs scraping (that is v1.1, JobSpy, only if v1 is clean).
- No changes to C8's files or state (own seen-list, own queue file).

## Tech
Python 3.12, standard library only for the runtime (urllib). pytest for tests; all HTTP
in tests is faked — no live calls in the suite.

## Verification
`.builder-os/init.sh` exit 0: pytest suite green + a --once dry smoke against fixture data.

## v2 (2026-10-25) — proxy-resilient, on-demand watcher (BUILDER-OS spec amendment)

### Why v2, why now
- v1 is shipped and green (54 tests passing, re-verified 2026-10-25), but its
  operating model is dead: the poll loop died with the 2026-10-25 VM replacement
  and its supervision cron was removed in the 2026-10-25 16:01 blanket schedule
  cancel. No new schedules/crons are authorised, so v2 is ON-DEMAND, not a loop:
  main or another chat invokes `--once` / `--audit` explicitly. `--loop` code
  stays in the tree but is not the supported operating mode in the new 4-chat
  machine.
- Live-cycle evidence (last cycles before the loop died): 29–32 boards ok,
  45–48 boards failed per cycle. Two failure classes dominate and both are
  fixable without any new schedule: (a) proxy-truncated responses
  (`IncompleteRead` on large Ashby payloads, e.g. Kantiv, Composio) and
  (b) 404s from unverified slug candidates (e.g. Darwinbox, Setu, Superkalam,
  Angel One on platforms they do not use). v2 fixes (a) by retry and (b) by
  quarantine + reporting, instead of burning a full cycle on dead boards.
- Supply is the binding constraint on the 250/day headline target, so a
  watcher that surfaces real new ATS postings on demand is worth more right
  now than any new portfolio project: no application is currently waiting on
  a build, and the only open project gaps are below the GAP trigger (see
  triage note in the build log).

### v2 behaviour (in addition to v1, v1 behaviour unchanged)
1. **Proxy-truncation retry (catch-008, UPHILL first).** On `IncompleteRead`
   / remote-closed mid-payload, retry the board fetch on a fresh connection,
   bounded (max 2 retries, same 20s timeout, polite delay kept). A board that
   still fails after retries is recorded as a board failure exactly as v1 does
   — retry never invents a posting, never replays a partial payload as complete,
   and never aborts the cycle.
2. **Dead-board quarantine (catch-009).** A board that 404s for N consecutive
   cycles (N=3, configurable) is quarantined: skipped by `--once` polls and
   listed in the audit report with its consecutive-404 count. Quarantine never
   deletes a catalog entry and never touches the seen-list; a quarantined board
   is re-checked only by an explicit `--include-quarantined` run or by a
   catalog edit, so a company that later opens a real board is recoverable.
3. **On-demand audit report (catch-010).** `--audit` prints one JSON report
   (stdout, no file side effects beyond reading state): boards ok/failed/
   quarantined in the last cycle, last-cycle timestamp and counts, queue depth
   (lines in job-catcher-queue.jsonl), and count of `triage_unavailable`
   queue items. This is the report main/other chats use to decide whether a
   `--once` cycle is worth running — no loop, no cron, no background process.

### v2 non-goals (in addition to v1)
- No new schedules, crons, systemd units, or background loops.
- No auto-deletion of catalog entries, no seen-list rewrites, no changes to
  the queue schema, no certification/pay verification/applying (v1 boundary
  stands), no browser, no login anywhere.
- No new portfolio claim: v2 is tooling, it adds nothing to his resume.

### v2 verification
- `.builder-os/init.sh` exit 0 (pytest + fixture smoke), plus a source
  secret-scan pass (exclude .venv/__pycache__) before any report of done.
- Every new feature carries evidence in feature_list.json + build-log.md;
  nothing is "done" until init.sh exits 0.
