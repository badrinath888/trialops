# User-workflow release checkpoint — 2026-10-10
- Base b7f886c; verified implementation/source commit follows this checkpoint.
- Scope USER-WORKFLOW-SPEC.md; rules AGENTS.md; no unrelated edits found.
- All three requested capabilities implemented and deployed locally3001.
## Relevant paths
- apps/api/user_workflow.py: personal queue, deterministic versioned next step,
  hashed/restricted links, text submission, current policy and human review.
- migrations/007_user_workflow.sql: additive policy/link/response schema.
- main.py/release_api.py/report.py: routes and token/contact-safe exports.
- reminders.py: existing durable request reminder channel for pending responses.
- apps/web/app/user-workflow-panels.tsx: Overview/case/request/settings panels.
- respond/page.tsx: restricted question only, memory-only token, no-referrer/no-store.
- lib.ts/evidence-workflows.tsx/workspace page: refresh/action routing and provenance.
- next.config.mjs/API proxy: same-origin/no-referrer security and token header routing.
- tests/test_user_workflow.py, user_workflow_integration.py, browser/user-workflow-check.cjs.
- USER-WORKFLOW-RELEASE.md: locations, security/limits, policy/config and rollback.
- USER-WORKFLOW-VERIFICATION.md: actual results, backup refs and coverage limits.
## Actual completed checks
- 57 unit tests;6 new workflow +15 existing +10 release +7 five-feature +5 boundary
  integration groups pass (43 groups). Production API/worker/web builds pass.
- Test/live populated browser journeys pass18 states each at1440/390, zero errors
  or overflow. Actual clipboard copy, anonymous restricted response, focus refresh,
  human consideration, current observation/check completion and separate resolution.
- Prior-feature browser regression passed16 states including reopening, imports,
  monitoring preparation, procedure reassessment and actual worker evaluation.
- Full20-page sample PDF rendered/visually inspected; JSON/PDF response attribution,
  review decisions and token/recipient exclusion verified. No new inference added.
- Fixed checklist ownership lookup, minimum/invalid text validation, queue filtering
  before bounds, withdrawn review eligibility, secret-in-response rejection and
  open-pane focus refresh. Browser timing matchers were corrected without changing
  production limits or relaxing security checks.
## Deployment / preservation
- 007 applied3002 after separate restore verification of fresh test backup:
  trialops-verified-20261010-112050-45646.dump.
- Live writers quiesced; fresh backup restored into separate verification DB:
  trialops-verified-20261010-185338-6065.dump; SHA256 checked.
- Exact old application images retained pre-user-workflow-b7f886c.
- 007 applied live; only affected api/worker/web updated; final API/web refinements
  verified on3002 before updating3001. All live services healthy.
- Exact disposable browser samples cleaned; both original full-row DB fingerprints
  and private environment/secret/upload file hashes match. Volumes/backups retained.
## Remaining / next action
- NEXT: commit verified source/docs/tests only, then report completed release.
- No incomplete implementation or blocked work. Text-only bearer links do not
  verify identity/truth; GET budgets are per process; reminders follow scan cadence.
- Queue caps, volatile drafts, Chromium/two-width coverage limits documented.
## Commands (project root)
- Test prefix: docker compose -p trialops-release-test -f compose.yaml -f compose.release-test.yaml
- Unit: prefix exec -T api python -m unittest discover -s tests -p 'test_*.py'.
- Focused: prefix exec -T api python tests/user_workflow_integration.py.
- Browser: TEST_WEB_URL=http://localhost:3002 node tests/browser/user-workflow-check.cjs.
- Backup: bash scripts/verify-backup.sh (separate restore DB only).
- Live: docker compose run --rm --no-deps api python migrate.py;
  docker compose up -d --no-deps --no-build --wait api worker web.
- Rollback: docker compose -f compose.yaml -f compose.user-workflow-rollback.yaml
  up -d --no-deps --no-build --wait api worker web (schema/history retained).
- Never reset DBs, down -v, send external messages, expose tokens or publicly deploy.
