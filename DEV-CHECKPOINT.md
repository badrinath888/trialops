# Five-feature checkpoint — 2026-10-10
- HEAD cc838b7; previous fourteen features and assessments preserved.
- Scope: FIVE-FEATURE-SPEC.md; instructions: AGENTS.md.
- Uncommitted five-feature API/UI/schema/tests/config/docs; no unrelated edits found.
## Relevant paths
- apps/api/account_access.py: hashed purpose-bound tokens, generic recovery,
  bounded SMTP, verification, reset and complete session revocation.
- apps/api/five_features.py: scoped directory/handover/blockers/duplicate matching.
- main.py/security.py/models.py/release_api.py: auth, assignment guards, request
  contacts/overrides, JSON export; report.py: PDF history; reminders.py/worker.py:
  existing deadline channel and expired token cleanup.
- apps/web/app/five-feature-panels.tsx: compact directory/continuity/overview panels.
- evidence-workflows.tsx: request warning/reuse/override/contact editing.
- account-access/page.tsx: recovery/verification/reset; sign-in/settings integration.
- database/migrations/004–006: additive schema, contact audit and safe cleanup FKs.
- compose.release-test.yaml: isolated Mailpit SMTP1025/UI loopback8026.
- FIVE-FEATURE-RELEASE.md: configuration, threat boundaries, limitations, rollback.
- tests/test_five_features.py, five_integration.py, browser/five-check.cjs.
## Completed and actual checks
- All five capabilities implemented; test migrations004–006 applied only3002.
- 53 unit tests, 7 focused integration groups, 15 existing integration groups pass.
- Earlier unchanged release integration10 and boundary5 groups passed this scope.
- Production api/worker/web builds pass including final hashchange fix.
- Focused tests cover permissions/isolation, idempotency/concurrency, exact IDs,
  overlapping waiting time, contact archive, token hash/purpose/expiry/single-use,
  local mail, reset revocation, rates and token-free exports.
- Fixed same-page email-link navigation; full five browser journey passed18 states
  at1440/390, zero page errors. All13 PDF pages rendered/visually inspected.
- Broader original browser initially hit real rate limit; paced rerun passed16
  states, including approval/resolution/imports/monitoring/worker evaluation.
- Test backup restore verified before migration; original data fingerprints saved.
- Live fresh backup restore passed: trialops-verified-20261010-110431-38460.dump.
- Rollback images tagged pre-five-cc838b7; live004–006 applied successfully.
- Tested images deployed api/worker/web; all live services healthy.
- Live five-feature browser passed14 states, zero errors; email unconfigured.
- Exact fresh fixtures cleaned; both original DB fingerprints/private files match.
## Remaining and exact next action
- NEXT: none after source commit. Authorized five-feature release complete.
- Clean only exact fresh browser fixture IDs using cleanup_five_browser.py;
  compare both original permanent-record fingerprints via /private/tmp/five-invariants.py.
- Fresh restore-verified live backup, retain current image rollback tags, migrate
  and update only tested api/worker/web; health/live workflow/data checks.
- Final documentation complete; commit source only, excluding generated/private files.
## Commands (project root)
- Test prefix: docker compose -p trialops-release-test -f compose.yaml -f compose.release-test.yaml
- Test checks: prefix exec -T api python -m unittest discover -s tests -p 'test_*.py'
- Focused: prefix exec -T api python tests/five_integration.py
- Browser: TEST_WEB_URL=http://localhost:3002 node tests/browser/five-check.cjs
- Backup: bash scripts/verify-backup.sh (separate restore DB, never over existing DB).
- Live: docker compose run --rm --no-deps api python migrate.py;
  docker compose up -d --no-deps --no-build --wait api worker web.
- Rollback: docker compose -f compose.yaml -f compose.five-rollback.yaml up -d
  --no-deps --no-build --wait api worker web (retains additive schema/data).
- Never reset databases, down -v, send external test mail or publicly deploy.
