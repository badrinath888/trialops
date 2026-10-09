# Integrated TrialOps release verification — October 9, 2026

## Scope completion ledger

All fourteen original feature areas are implemented. No later proposed features
were added. Source/API checks were paired with the real running workflow tests;
UI checks use synthetic sample workspaces, never the permanent user account.

| # | Requirement and location | Executed evidence |
|---|---|---|
| 1 | Reviewed checks — Case → Evidence & follow-up → Checks | Frozen cited sources; human edits/save/activation; assessed evidence; role and concurrent version checks; browser |
| 2 | Missing information — Case → Information requests | Structured requests, owners/deadlines, received response evidence, overdue reminders, stale write rejection; browser |
| 3 | Immutable snapshots/comparison — Case → Comparisons & related cases; Operational records history | Immutable scoped snapshots, stable-record diffs, idempotency, historical run preservation; browser |
| 4 | Evidence-backed resolution — Case → Supporting observations and Case status | Approval separate from closure; current-cycle verification, assessed checks, reviewer rationale, reopening audit, invalid/duplicate/stale resolution rejection; browser |
| 5 | Related cases — Case → Comparisons & related cases | Scoped suggestions/differences; human-confirmed links; linked cases remain open; browser |
| 6 | Measured activity — Overview; Case → Human effort | Separate queue/worker/review/cycle timings; idempotent explicit human minutes; ROI assumptions stay separate; browser |
| 7 | Freshness/conflict flags — Case comparisons; Settings → Data policy | Stable entity IDs, conflicting statuses, missing records and configured freshness; scenario evaluation/API tests |
| 8 | Procedure changes — Knowledge → Procedure changes and reassessment | Retained versions/diffs, changed-procedure notices, explicit rationale; prior approvals frozen; browser |
| 9 | Monitoring preparation — Operational records | Dated study/site inventory, configurable assessed visit checks and summary export; version protection; browser |
| 10 | In-app reminders — Overview; Settings → Data policy | Worker scans, condition-key deduplication, personal preferences/read state; durable/private API regression; reminder UI |
| 11 | CSV/JSON preview — Operational records | Field mapping, rejected rows, scoped timestamps, immutable-ID conflict, expiry, explicit atomic commit/replay; browser |
| 12 | Complete case package — Case → Case package JSON/PDF | Populated export includes frozen sources/records/drafts, checks/responses/comparisons, decisions/events/current resolution; all 23 PDF pages rendered and visually inspected |
| 13 | AI evaluation — Knowledge → AI evaluation dashboard | Actual nine-scenario procedure worker evaluation, recorded config/hash/results; interruption/retry and lost-lease tests; browser. Previous Ollama evaluation retained (see below) |
| 14 | Sample walkthrough — Overview in sample workspace | Persisted progress, skip/resume, updated observations idempotent and sample-only; browser |

## Executed checks

- **42 unit tests passed** on the preserved port 3002 stack.
- **15 existing integration groups passed**, including the actual worker/MCP path,
  workspace isolation, signup/invitations, unsupported evidence and lease expiry.
- **10 release integration groups passed**, covering all fourteen feature areas.
- **5 boundary groups passed**: simultaneous policy/intake writes, preview expiry,
  interrupted evaluation/retry, lost worker lease, empty-workspace responses.
- **16 populated release browser states passed** at 1440px and 390px, with 2,991
  measured text instances and no recorded JavaScript/contrast/control/overflow
  failures. The journey completes imports, monitoring, reassessment and evaluations.
- **54 broader browser states passed**, including saved-investigation tabs,
  desktop/narrow routes, case search, keyboard table scrolling, mobile menu Escape
  and focus return, account preferences, validation and short-sidebar scrolling.
- **Related-case typography regression passed** at both widths after fixing the
  verified title/explanation collision. Production web build and TypeScript passed.
- API/worker production images built; final web image built after the CSS fix.
- **Complete 23-page case evidence PDF** rendered with Poppler; all pages inspected
  on four contact sheets. No clipping/overlap found. Long audit payloads produce a
  lengthy document; the final page contains the remainder of resolution evidence.
- **Nine procedure-mode evaluation scenarios passed** during integration and browser
  runs. The previously completed **nine Ollama qwen2.5:7b scenarios** also passed:
  dataset `trialops-scenarios-1.0.0`, executed October 9 at 09:41 Chicago time,
  zero execution failures and 9/9 citation, abstention, escalation-rule and flag
  assertions. That earlier model run was inspected. The deployed browser smoke also ran
  the installation's configured Ollama mode: nine scenarios passed again with
  zero execution failures and all four deterministic assertion groups at 9/9.
- **Four additional populated browser states passed** on port 3002: real worker
  overdue reminders, persisted read state after reload and policy-derived freshness
  flags at desktop/narrow widths. A disposable sample workspace was used; the
  actual durable scan was invoked after renewing only that sample scan marker.
  Screenshots visually inspected.
- `git diff --check` passed.

The earlier release browser report was incomplete: a rapid screenshot journey
exhausted the real 180-request/minute session limit. The test now waits for budget
renewal before Operations. Production limits were preserved. The live installation defaults to Ollama,
so the browser test now explicitly selects procedure evaluation before asserting
its model label. The first live evaluation itself passed in Ollama mode. An exact-label test
selector also needed correction because the select options are part of its
implicit label. The final journey explicitly opens Measured workflow activity;
earlier Overview captures left that disclosure collapsed. One related-case
spacing defect found by visual inspection was fixed and rechecked.

## Deployment and preservation

- Fresh port 3001 backup: `backups/trialops-verified-20261009-175853-13673.dump`.
  Restore into a separate temporary database succeeded: 8 users, 8 workspaces,
  67 cases, 9 investigations, 42 procedures; vector extension present. SHA-256
  sidecar recorded. Application writers were stopped before this archive.
- Fresh port 3002 backup: `backups/trialops-test-verified-20261009-175905-13823.dump`.
  Independent restore succeeded: 22 users/workspaces, 206 cases, 19 investigations,
  111 procedures; vector extension present. SHA-256 sidecar recorded. This is a
  transaction-consistent backup while the isolated stack remained available.
- Applied checksum-verified `001_integrated_workflows.sql` and
  `002_workflow_concurrency.sql` on port 3001. Migration replay was a no-op.
- All pre-existing live user/case/run/knowledge/operation/event content fingerprints
  matched after migration. Additive case submission field was excluded from the
  fingerprint as intended. Original database container/volume retained.
- Permanent-data fingerprints also matched after service replacement: live has
  1 permanent account, 9 cases and 1 investigation; test has 5 permanent accounts,
  42 cases and 3 investigations. Its single permanent draft checklist matched
  exactly. User test account and records were preserved. No database was reset.
- Only port 3001 API/worker/web replaced. All are healthy. Port 3002 had only its
  web service replaced for the typography fix; its API/worker/database preserved.
- Rollback application images saved locally; commands in RELEASE-2.0.md and
  compose.rollback.yaml. Existing `.env` and mounted secrets preserved.
- Full post-deployment browser workflow **passed** in a fresh sample workspace:
  16 states, 2,957 measured text instances, no recorded measurement/JavaScript
  errors. Includes investigation/review/checks/request response, resolution/reopen,
  exports, preview/commit, monitoring, reassessment, evaluation and expanded
  populated metrics at both widths. Permanent fingerprints still match afterward.

## Coverage and practical limits

Headless Chromium at simulated desktop/narrow widths does not establish Safari,
Firefox, real-device or screen-reader behavior, or complete WCAG certification.
Automated measurements cover rendered text/controls; manual screenshot review
focuses on populated workflow panels and saved investigations. Reminders were
populated/asserted through real worker/API and browser checks; no external
messages exist.
Evaluation uses versioned supplied synthetic sources, not a live retrieval or
clinical validation benchmark; subjective usefulness is separately recorded.
Import is intentionally limited to generic synthetic records. Historical procedure
versions that were not retained cannot be reconstructed. Bounded local list limits
and canonical escalation-rule restrictions are documented in RELEASE-2.0.md.
Rollback API/worker imports, web server syntax and Compose configuration were
verified, but the
full older stack was not activated over the live database. No public deployment,
service purchase, external sending or unauthorized permanent-workspace mutation
was performed.
