# Build Log — Job-Catcher v1

## Summary
ATS watcher per main's execution order 2026-10-23 (Problem 2 fix): polls Greenhouse/Lever/Ashby
public JSON feeds for the watchlist catalog, diffs against its own seen-list, deterministic
fresher filter + OmniRoute triage on new postings, survivors to hidden_files/job-catcher-queue.jsonl
for C1/C11. It never certifies — downstream gates unchanged.

## Decisions made
- Reused C8's catalog (hidden_files/watchlist_sources.json, 126 companies / 72 boards) and its
  endpoint shapes (incl. Ashby ?includeCompensation=true); catcher keeps its OWN seen-list —
  no writes to C8's files or state.
- Xobin list does not exist as a standalone file yet (it is C8's Wave-1 sweep); catalog loader
  merges hidden_files/xobin_sources.json automatically when it lands.
- Baseline-seed first run (queue nothing) so C1/C11 are not flooded with the standing catalog.
- Triage degrades to KEEP + triage_unavailable on any OmniRoute failure — never silently drops.
- Loop hosting: systemd user bus is unavailable on this VM, so the loop runs as a setsid nohup
  process (PID in .builder-os/loop.pid, output in job-catcher-loop.log) with a daily cron
  liveness check that restarts it if dead.

## FCAR record
- Round 1: FAIL — seen-list keyed on bare job_id silently dropped postings across boards
  (probe-proven). Fixed: composite platform:slug:job_id identity everywhere + regression tests;
  plus filter/spec amendment (specs.md section 4), --runs-log pass-through (tests no longer
  pollute the production run log), corrupt-seen guard (backup + baseline re-seed), dead-code
  removal, smoke step added to the verify gate.
- Round 2: 6/7 fixes verified; one residual — a sub-3 range's upper bound ("1-3 years of
  experience") re-matched as a standalone demand. Fixed exactly as prescribed (ranges judged
  first, spans masked) + regression tests; load_seen hardened so valid-JSON-but-scalar content
  also counts as corruption. No third round: the fix implements the reviewer's own prescription
  and its probe cases are pinned as tests (34 passed).

## Evidence
- Smoke test (live, 2026-10-23): Greenhouse/Stripe HTTP 200 728 jobs 2.4s; Lever/CRED 200 8 jobs
  2.0s; Ashby/Sarvam 200 42 jobs 1.4s.
- Test suite: 34 passed (final). Verify gate .builder-os/init.sh exit 0: pytest + fixture smoke
  ("SMOKE OK: baseline seeded 2 colliding-id postings, cycle 2 queued exactly the 1 new posting").
- Secret scan (BUILDER-OS): PASS, no secrets; the OmniRoute key is read from
  ~/.config/omniroute-local/client_key at runtime and never logged.
- Live baseline + loop launch: recorded below once run.
- LIVE BASELINE (2026-10-23 ~12:00 IST): first real cycle — boards_ok=31, boards_failed=45
  (unverified slug candidates 404ing, as designed; failures are data, logged per board),
  postings_seen=2834 seeded into hidden_files/job-catcher-seen.json (composite keys),
  queued=0 (baseline). Queue file correctly not created.
- LOOP LIVE: setsid nohup loop, interval 600s, PID in .builder-os/loop.pid; output to
  job-catcher-loop.log; run log job-catcher-runs.jsonl. Supervision: daily cron
  job-catcher-loop-watch (~09:46 IST) restarts it if dead and reports only then.
- Post-launch fix (same day): board-failure log lines now include the platform
  ([platform:slug]) — the first live logs showed 404s on verified companies' NON-home
  candidate slugs, indistinguishable from real failures without it. Verified directly
  that the verified home boards all answer 200 (CRED Lever 8 jobs, Zeta Lever 27,
  Razorpay Greenhouse 25, Hevo Lever 53, Stripe + Sarvam from the smoke test).
  Suite re-run 34 passed; loop relaunched clean (PID recorded in .builder-os/loop.pid).
- FILTER v2 + TRIAGE REPAIR (2026-10-23 evening, throughput-plan order): v1's first
  catch-up cycle queued 6 items, all noise (Head of AI Startups EMEA; SDE-II Android;
  Marketing internship; Executive Assistant NYC; SDE Remote-Ireland; Creative &
  Comms intern). Root causes: (1) OmniRoute was DOWN -> triage degraded to keep-all
  (by design) with triage_verdict=triage_unavailable stamped; (2) the negative-only
  filter had no level markers, no role-family gate, no location gate.
  Fixes: OmniRoute revived (triage probe returns KEEP in ~10s); specs s.4 amended;
  filter v2 = extended seniority (vp/head/chief/architect) + level markers (II/III,
  SDE-2/3, L2/L3) + positive role-family gate + India location gate (explicit
  foreign location with no India signal dies; unstated/country-less Remote passes).
  53 tests (19 new; the 6 real noise items are fixtures), gate exit 0. One old
  fixture corrected ("Dev" placeholder title -> "Developer").
  Queue hygiene: all 6 v1 items re-run through v2 - 0 kept, 6 moved to
  hidden_files/job-catcher-queue.rejected-2026-10-23.jsonl with kill reasons.
  Loop relaunched on v2 (PID in .builder-os/loop.pid).
- LOOP DEATH 2026-10-23: the loop died ~14:27 IST when the VM was replaced; the
  daily supervision cron could not catch it for ~19h. Supervision cron
  job-catcher-loop-watch tightened to every 2h (staleness threshold 3h).
  Final pre-death cycles also degraded (boards_ok 31 -> 4-7) on proxy-truncated
  responses (IncompleteRead / remote-closed; zero 429s) - network, not ATS limits.
- 2026-10-24 ~00:20 IST (watch cron): loop dead AGAIN after another VM replacement
  (last good cycle 22:33:42 IST). The cron's own relaunch (PID 7809) did not hold;
  C6 relaunched and verified alive. Queue at the time: 5 items, all
  triage_unavailable because OmniRoute was ALSO down (daemon's health endpoint
  answered but its completions worker was dead - stale fork; upstream Gemini
  itself verified healthy at 0.78s). Fresh daemon fixed it: completions 200 in
  4.3s, triage probe KEEP.
- Sao Paulo gap: "Full Stack Software Engineer, Brazil" carried location
  "Sao Paulo" (unaccented, no country), which the v2 foreign list missed - added
  `sao\s*paulo` to FOREIGN_LOCATION_PATTERN (+ regtest), gate re-run 54 passed,
  loop restarted on the patch. The item moved to the rejected file.
- Watch cron body now also revives OmniRoute on failure (the untriaged-queue
  signature = triage_unavailable items), keeping the 2h cadence.
