# Case watch verification — 2026-10-11 (base e3c4e69)

## What it does
Reviewers (owner/reviewer) can Watch / Pause / Resume / Stop watching an open case from the case page ("Case watch" panel).
Watched inputs only: new information-request responses (recorded and external), new snapshots for the case's study/site,
changes to explicitly selected evidence, and newly human-confirmed linkage decisions. Changing settings re-baselines.

## Design
- `apps/api/case_watch.py` (one module, no new dependency): worker scan every 10s -> state must be stable 15s (bursts combine)
  -> unique durable `watch` job per case (max 3 queued/running per workspace, 20 active watches) -> deterministic diff vs saved cursor
  -> update built from deterministic facts -> optional bounded local-model question phrasing (reuses `assess('questions')`:
  20 KB input, 60s timeout, 2 attempts, validated citations) -> authorization/lease/cursor re-checked, then persisted.
- Reused: jobs/leases/recovery, `fresh_actor`, `select_sources`, `linkage`, `gaps`, `assess`, notifications, `case_events` audit, case package/PDF.
- Migration `008_case_watch.sql` is additive (`case_watches`, `case_watch_updates`, job kind `watch`).
- Deterministic: change detection, exact-identifier linkage, uncertainty, next action. Labelled model output appears only in
  `model` (question/uncertainty/citations); no reasoning is stored. External response text is never sent to the model or copied.
- Same-site records are never linked; only exact identifiers without conflict are reported, and always as unconfirmed.
- Older updates are kept; superseded or changed-evidence updates are marked stale. States: off, paused, watching, change detected,
  processing, failed (explicit retry), unavailable (resolved case). Interrupted jobs recover automatically (max 3/10 min).

## Checks actually run (test stack, port 3002)
- `tests/test_case_watch.py` 9 unit tests; full unit discovery 66 passed.
- `tests/case_watch_integration.py` 10 groups: dedup, burst, pause/disable/mid-run pause, workspace isolation, revoked permission,
  stale results, malicious snapshot identifiers and hostile external text, model outage/invalid output, interrupted-job recovery,
  failed+retry, workload bound, JSON/PDF export (run with the test worker stopped).
- `tests/browser/watch-check.cjs`: enable -> unrelated failed job unconfirmed -> correct receipt arrives -> update explains exact
  identifiers/uncertainty/next action -> notification -> reviewer records an observation separately, case stays open -> pause ->
  export has watch history; no horizontal scroll at 1440/390; zero page errors.
- Regression: design-check 29, visual-review (54 pages, no issues), user-workflow-check, release-check, plus
  user_workflow_integration (6), release_integration (10), five_integration (7).

## Limits
- In the browser journey the local model (qwen2.5:7b) answered but the existing question validator rejected its output
  ("Invented or duplicate uncertainty gap"), so the update was deterministic only and said so. A successful model path was
  tested with an injected model only. `assessment_integration.py` (live Ollama) was not rerun; assessment code is unchanged.
- Scan interval is polling (10s + 15s stability), not instant. Watches do not cover resolved cases. Chromium only.

## Deployment / preservation
- Fresh live backup restore-verified before migration: `backups/trialops-verified-20261011-180814-86773.dump` (+ .sha256; ignored by Git).
- Live permanent-record fingerprint equal before/after; DB container not restarted. api/worker/web redeployed to 3001 only.
- Rollback images `trialops-release-{api,worker,web}:pre-watch-e3c4e69`;
  `docker compose -f compose.yaml -f compose.case-watch-rollback.yaml up -d --no-deps --no-build --wait api worker web`.
  Migration 008 stays (additive). Browser suites were not run live (they create sample workspaces); live checks: 200, unauthenticated
  watch API 401, new bundle present, worker healthy.
