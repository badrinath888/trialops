# Integrated TrialOps release plan

## Recovered baseline

- [x] Inspect dirty Git tree and preserve previous edits.
- [x] Verify local browser review: 54 states, 3,839 measured text instances, no recorded failures; inspect standalone saved-investigation desktop/narrow screenshots.
- [x] Confirm current service health and prior web-only container replacement evidence.
- [x] Finish LOCAL-BROWSER-REVIEW.md and retain screenshots under artifacts/ui-review.

## Implementation milestones

- [x] Inventory instructions, schema, API, worker, evidence policies, exports, frontend, tests, deployment and backup workflow.
- [x] Add repeatable migrations and isolated release test environment; preserve an inventory of existing-data invariants.
- [x] Implement guided checks, missing-information requests, evidence-backed separate resolution, related cases and audit/concurrency protections (features 1, 2, 4, 5).
- [x] Implement immutable snapshot history/comparisons, freshness/conflicts, procedure versions/impact and validated idempotent preview imports (3, 7, 8, 11).
- [x] Implement measured workflow metrics, monitoring preparation and durable in-app reminders/preferences (6, 9, 10).
- [x] Extend case evidence PDF/JSON exports, versioned AI evaluations and resumable sample walkthrough (12, 13, 14).
- [x] Integrate compact graphite/copper UI into existing navigation with loading/error/permission states.
- [x] Run unit/integration/security/concurrency/worker retry tests and full browser journey in isolated environment.
- [x] Inspect populated desktop/narrow screenshots and fix verified defects; production-build affected services.
- [x] Create and restore-verify backup of existing installation before applying migrations.
- [x] Deploy only affected services; verify health, migrations and preserved existing-data invariants.
- [x] Update release/configuration/migration/rollback documentation, record exact results and limitations, commit verified source without secrets/generated outputs.

## Required verification ledger

Sign in/switch, intake, investigate, frozen citations/records, reviewed check activation/completion, missing-info response, updated import/comparison, related-case confirmation/conflict flags, recommendation decision, separate current-evidence resolution, reopening, complete export, metrics/notifications/history.

Failure boundaries: unsupported/stale/missing/conflicting evidence, procedure changes after approval, workspace/role access, invalid/duplicate imports, stale/concurrent writes, interrupted worker/retries, keyboard/focus, long content/tables, empty workspaces, authentication/sign-out, backup/restore.

Each milestone will be updated with actual implementation and executed verification. Unimplemented requirements remain open; no placeholder counts as complete.

## Resumed checkpoint — 2026-10-09

- Inspected plan, source diff, migrations, both healthy stacks, prior reports/screenshots and logs. Prior release browser journey stopped at the session rate limit; it was not a complete pass.
- Rerun: 42 unit tests, 15 baseline integration groups, 10 release integration groups, 5 concurrency/retry boundary groups passed. Only temporary test records were removed by test cleanup.
- Completed release browser journey: 16 populated states, 2,991 measured text instances, no reported errors/measurement issues. Broad visual journey: 54 states, no issues, including saved investigations, desktop/narrow and keyboard/focus.
- Rendered all 23 case-package PDF pages and inspected all four contact sheets; no clipping/overlap. Generated outputs remain ignored.
- Fixed confirmed related-case title/explanation spacing in globals.css; isolated web rebuild/recheck pending.
- Browser test now waits for session budget renewal before Operations; production rate limits unchanged.
- Current permanent fingerprints are under ignored artifacts/release/resume: live has 1 account, 9 cases, 1 run; test has 5 accounts, 42 cases, 3 runs, 1 draft checklist. User test data must be preserved.
- Production api/worker/web images built; existing live services have NOT been replaced. Exact rollback images are being preserved via docker export/import because Docker no longer has the original content digests (tag/commit failed). API and worker rollback images saved; web export in progress.
- No database reset, no live migrations yet. Fresh stopped-writer backup/restore verification, live deployment, post-deploy invariant checks, final docs and commit remain.

### Deployment checkpoint

Fresh live/test backups restored successfully (filenames in RELEASE-VERIFICATION.md).
Both additive migrations applied once; replay no-op. All old live content matched
immediately after migration. Original DB container retained; only live api/worker/web
replaced. Both stacks healthy. All permanent account/data fingerprints and the test
account's draft checklist unchanged. Corrected related-case typography passed both
browser widths. Rollback export/import images saved and API runtime verified;
compose.rollback.yaml contains application-only rollback selectors.
Full deployed sample browser journey has completed case workflows/export/reopening,
import and monitoring and is currently verifying Knowledge/evaluation/Overview.
Final post-deploy result, documentation completion and source commit remain.

Final browser-check corrections: explicitly choose procedure mode on the live
Ollama-configured installation; match the implicit Evaluation mode label without
exact matching; expand Measured workflow activity before Overview captures.
The deployed Ollama evaluation passed 9/9. A final full live journey with all
corrections is now running (output /private/tmp/trialops-live-complete).

Reproducibility: the browser test also waits for the explicit-human-effort metric
label after opening measured activity. Generated verification screenshots/PDFs
are retained under ignored artifacts/release/resume. Both fresh backup checksum
sidecars verify. All 52 staged files are vetted source/tests/documentation;
private/generated paths and private-key/API-key patterns were excluded.

### Final live journey result

PASS: complete deployed browser journey, 16 states, 2,957 measured text instances,
no reported issues/errors. Visually inspected expanded metrics at both widths: real
queue/execution/review/cycle timing and 8.5 explicit human minutes are populated.
Both permanent-data fingerprints still match after completion. Additional
populated reminder/flag browser check is running in a new port 3002 sample only.

## Completion checkpoint

All fourteen original features completed and verified; no later features added.
Populated reminders/read persistence and freshness flags passed four additional
desktop/narrow browser states; screenshots inspected. Complete live journey
passed 16 states, and broader test review passed 54 states. Both databases and
the user-created test account/run/draft checklist are preserved. Fresh backups
restore-verified; additive migrations applied; all eight services healthy.
Release/configuration/rollback/limits documented in RELEASE-2.0.md and
RELEASE-VERIFICATION.md. All source/test/docs are included in the authorized commit;
no private/generated artifact is staged. No functional scope item remains open.

Final evidence is saved in ignored artifacts/release/resume/live-journey and
related populated reminder/flag images. Fresh-sample snapshot history confirmed
present (one immutable baseline per study/site); unselected native selectors
show their choice prompt until the reviewer selects a snapshot.
The verified release is committed with this completion checkpoint;
all remaining limits are coverage/scale limitations, not unfinished scope.

Connected capability extension checkpoint and ledger: ASSESSMENT-PLAN.md. Original fourteen-feature completion remains intact; extension delivery/results: CONNECTED-ASSESSMENTS.md and ASSESSMENT-VERIFICATION.md.

Final connected-capability checkpoint: implementation, semantic/security/browser
verification, complete PDF/JSON review, fresh restore-verified backups, additive
migration003 and affected-service local deployment complete. Both original
databases/accounts/run/checklist fingerprints preserved. Live3001 healthy and
full isolated sample workflow passed. See ASSESSMENT-VERIFICATION.md for exact
results/coverage limits; source commit follows.
