# Visual refinement checkpoint — 2026-10-10
- Base/source c8cc0d6; prior completed release checkpoint 9fe1132.
- Git initially clean; current edits: shared CSS, MyWork presentation, auth/settings copy, focused UI tests.
- Scope: cohesive graphite/ivory/copper refinement across all existing UI routes.
- No backend, authorization, schema, security, inference or workflow changes.
## Relevant files
- apps/web/app/globals.css: shared tokens, serif headings, quiet divider sections,
  consistent controls/tabs, responsive spacing, selective dark bands, reduced motion.
- sign-in/workspace page: accurate recovery copy and recovery-link placement.
- tests/browser/design-check.cjs: explicit empty/loading/error/long/unsaved/keyboard states.
- apps/web/app/user-workflow-panels.tsx: five initial personal items + expandable rest;
  existing links/actions retained; removed implementation-oriented queue commentary.
- tests/browser/visual-review.cjs: all-page populated desktop/narrow visual/accessibility.
- tests/browser/workflow-check.cjs: dialogs, unsaved editor, keyboard/preferences.
- tests/browser/user-workflow-check.cjs: guided action/external response/full case journey.
## Completed / actual checks
- Inspected applicable AGENTS, Git/checkpoint and affected shared UI components.
- Initial production build/type checks passed. All-page visual check:54 states,
  4,562 computed contrast text samples; no contrast/overflow/text/control violations.
- Focused state checks:26 passed (empty/public/long/loading/error/unsaved/focus/motion).
- Screenshot contact sheets and readable case/auth crops visually inspected.
- Found/corrected stale recovery copy and shortened next-step band after inspection.
- Final production build/type checks passed; final visual54 + state29 + five18 +
  guided/external-response18 browser states pass; zero page errors.
- Screenshot sheets and readable case/auth crops inspected; reduced-motion scroll fixed.
- UI-REFINEMENT-VERIFICATION.md records actual scope, checks, limits and web rollback.
## Exact next action
- DONE 2026-10-10: Overview reorder/tabs built on 3002; design-check 29, visual-review 54,
  user-workflow-check, release-check (16 states, 0 errors) pass. Web-only deploy to 3001;
  live DB fingerprint unchanged vs immediately pre-deploy; api/worker/db untouched.
- Rollback image trialops-release-web:pre-visual-9fe1132 verified. No earlier full DB
  baseline existed in /private/tmp; preservation claimed only from pre-deploy fingerprint.
- Remaining: none for this UI release. Rollback: compose.ui-rollback.yaml (web only).
- 2026-10-11 DONE: Overview band restyled (divided graphite strip). Non-zero counts link to
  /workspace/cases (?view=review|overdue); review/overdue >0 get copper underline; zero shows
  "None" (not a link). visual-review caught 14px link text; fixed to 15px, test web rebuilt.
  design-check 29 + visual-review 54/9 interactions pass; targeted Overview check passed
  (1440/390, links, zero state, keyboard focus, no h-scroll). Web-only deploy to 3001;
  live DB fingerprint unchanged; api/worker/db untouched. Nothing remaining.
## Case watch agent (2026-10-11) — DONE, deployed to 3001
- 008_case_watch.sql, apps/api/case_watch.py, worker dispatch/scan, export in release_api.py/report.py, apps/web/app/case-watch.tsx.
- Verified: unit 66, case_watch_integration 10 groups, watch-check journey, design/visual/user-workflow/release browser checks.
  Details/limits in CASE-WATCH-VERIFICATION.md (local model output was rejected by validator in the sample run; deterministic path ok).
- Backup restore-verified before migration; live DB fingerprint unchanged; rollback: compose.case-watch-rollback.yaml (api/worker/web).
- Real-model follow-up DONE: prompt/schema contract fixed (one question per gap), validation unchanged; see CASE-WATCH-VERIFICATION.md. api/worker redeployed; rollback tag pre-model-contract-0e96415.
- Evidence boundary DONE (validate_text trusts structured ids/times only; sanitized model.failure); rollback tag pre-boundary-e9eee72. Report: CASE-WATCH-VERIFICATION.md.
- Remaining: none required. Real-model checks: docker exec test-api python /app/tests/real_model_watch_check.py.
## Commands (project root)
- Test: docker compose -p trialops-release-test -f compose.yaml -f compose.release-test.yaml
  build web; same prefix up -d --no-deps --no-build --wait web.
- Browser: TEST_WEB_URL=http://localhost:3002 PLAYWRIGHT_MODULE=./node_modules/playwright
  CHROMIUM_PATH='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
  node tests/browser/visual-review.cjs (module resolved relative to test script).
- Live: docker compose up -d --no-deps --no-build --wait web after tested image tag.
- Migrations apply at api start (python migrate.py); backup first: bash scripts/verify-backup.sh. Keep old images for rollback.
- Preserve all DBs/accounts/uploads/private files; never reset or send externally.
- 2026-10-12: trust-boundary follow-up (procedure/case text ids rejected, elapsed-time rule) + case-search test waits for response; api/worker live; see CASE-WATCH-VERIFICATION.md.
- 2026-10-13: public-beta prep (local only, nothing deployed/purchased): APP_PUBLIC_URL from DOMAIN in compose.production.yaml; TRUST_PROXY web client-IP; tests/proxy_ip_check.sh passed on 3002; scripts/backup-offsite.sh tested only with an rclone SHIM (no real offsite, no real remote restore). Live 3001 not redeployed.
- 2026-10-13: demo prepared (DEMO.md, compose.demo.yaml, demo.sh, tests/demo_check.sh) on 3003; tunnel NOT opened, cloudflared not installed; 3001/3002 untouched.
- 2026-10-13 START five enhancements (base 68b4a94): migration 009_improvement_workflows.sql written; plan: apps/api/improvement.py (router: recurrence/prevention, readiness, procedure impact review, bulk cases, feedback queue), UI panels in apps/web/app/improvement-panels.tsx mounted in case page / Operations / Knowledge / CaseList / Feedback; tests tests/improvement_integration.py + browser improvement-check.cjs; nothing deployed yet.
- backend written (improvement.py, main/release_api/report wiring, migration 009); next: build test api, unit/integration tests, then UI
- backend + tests/improvement_integration.py (11 groups) PASS on 3002 test API; next: UI panels, browser journey, regressions, backup, live deploy
- UI done (apps/web/app/improvement-panels.tsx; mounted in page.tsx/case-list.tsx; proxy allowlist updated); tests/browser/improvement-check.cjs PASS on 3002; next: regressions, docs, backup+live deploy of api/worker/web (NOT 3003)
- 2026-10-13 DONE five enhancements, commit 4c2942e (docs: IMPROVEMENT-WORKFLOWS.md). 3002: unit 79, improvement_integration 11 groups, case_watch_integration 10, improvement-check journey (desktop+390px), design-check 29, visual-review (0 issues), user-workflow-check, release-check, watch-check pass.
  visual-review case-search step now waits for rendered state (earlier response-wait fix matched the wrong URL; an unexplained response timeout once in the full run, not reproduced in isolation 6/6).
  Live 3001: fresh restore-verified backup backups/trialops-verified-20261013-184330-3542.dump; migration 009 applied; api/worker/web redeployed; rollback tags pre-improvement-68b4a94; fingerprint unchanged. 3003 demo untouched (old image snapshot, no migration).
- 2026-10-13 UI cleanup (uncommitted, 3002 only; 3001/3003 untouched): bordered Investigations entries, sans identifiers (Operations headings, history meta, landing tag), wording trims + shared plural() in lib.ts, single-version procedure note, 15px figcaption. Checks on 3002: build/types, design-check 29, visual-review 54/9 (needs 65s pause before case-search step: 180 req/min session limit), improvement/user-workflow/release checks pass. Awaiting visual approval before live deploy.
- 2026-10-13 UI round 2 (uncommitted, 3002 only): Operations disclosures + Document readiness first, Knowledge disclosures, sample-walkthrough reveal-on-open (lib.revealOpened), compact sidebar identity, alignment fixes (policy grid, Data policy spacing, ROI preview, intake button, Knowledge Version header, narrow empty table). Targeted checks only; no full suites; 3001/3003 untouched.
## Document journey (2026-10-13, uncommitted, 3002 test stack only; 3001/3003 untouched)
- Backup before migration: backups/test3002-pre-journey-20261013-221247.dump (test DB; restored into a temp DB, counts matched: 509 cases/63 workspaces/9 migrations; temp DB dropped).
- Migration 010_document_journey.sql (additive; 7 new tables, no existing table altered): journey_exports/subjects/links/assessments/plan_items/outcomes/verifications. Applied on test API start.
- apps/api/journey.py: deterministic engine (normalize_export, classify/identity/destination, assess_stage, build_journey, evaluate/overall) + routes under /cases/{cid}/journey* and /operations/journey-import. Wired in main.py; case_package (release_api.py) + report.py export new sections.
- Reused: request workflow (create_request: duplicates, contacts, drafts), writer/role checks, audit events, case package/PDF, workspace freshness policy. Not reused: existing assessment linkage decisions (they join snapshot records, not source-scoped exports) — journey_links is a parallel reviewed-link table. Request responses are never used as evidence.
- UI: apps/web/app/document-journey.tsx mounted after CaseWatch in workspace/[[...path]]/page.tsx; CSS appended (.journey-*) to globals.css. Proxy allowlist unchanged (cases/operations already allowed).
- Tests: tests/test_journey.py (25 unit), tests/journey_integration.py (10 groups), tests/browser/journey-check.cjs (screenshots in artifacts/journey-screenshots).
- Next: visual approval; no live deploy. Live would need backup + migration 010 + api/web rebuild; rollback = old images (migration is additive).
- Results (3002): unit 104 pass (25 new); journey_integration 10 groups; improvement/case_watch/release integration pass; design-check 29; journey-check pass (1440+390, no overflow). release-check now fails at a pre-existing stale step ('Preview CSV/JSON record import' text no longer exists in source, unrelated); it also needed a 65s pause before CASE-4 (180 req/min session limit) which was added.
## Document journey follow-up (2026-10-13/14, uncommitted, 3002 only)
- Migration 011_journey_provenance.sql (additive): journey_links.snapshot_decision_id, journey_attestations. Applied on the 3002 test DB only (010+011 never applied elsewhere). Test api+web rebuilt; 3001/3003 untouched (uptimes unchanged).
- release-check fixed: stale locators updated (".bulk-import > summary", "Procedure changes and reassessment", "AI evaluations", Observation type -> human_observation); 429-bounded retry (4x20s) in its API helper + two pacing waits; app limits untouched. FULL run passes (16 states, 5 interaction groups incl. previously unexecuted import/reassessment/evaluation).
- Freshness (tests/browser/journey-freshness-check.cjs): no policy -> verified; 2h policy + 5h-old evidence -> insufficient, labelled stale; 12h -> verified; evidence before remediation -> insufficient; policy restored (null).
- Responses: existing review only marks accepted responses 'accepted for consideration, establishes_truth false' (no structured path). Added POST /cases/{cid}/journey/attestations (reviewer/owner): reviewed external or recorded request responses only; structured fields validated; provenance/reviewer/dates stored. Attested records are context only: stage stays unknown, outcomes stay insufficient.
- Links: journey_links needed because existing confirm_link decisions join unnamed-source snapshot records. Explicit adoption (snapshot_decision_id) validates exact structured matches, document, workspace, staleness; duplicate active link -> 409; links stop applying after definition change. Snapshot-only links listed separately in the UI.
- Semantics: only failed/not_visible on an exact record contradicts; pending/other mismatch, wrong version/binder, unknown destination -> insufficient.
- Tests: unit 109 (30 journey), journey_integration 10, journey_provenance_integration 3, improvement 11, case_watch 10 (one transient failure on first run, passed on rerun), design-check 29, journey-check/-freshness-check/-provenance-check pass.
## Suggested request order (2026-10-14, uncommitted, 3002 only)
- Backup before migration: backups/test3002-pre-priority-20261014-104828.dump (restored to temp DB; 611 cases/11 migrations matched; temp DB dropped). Migration 012_journey_priority.sql (additive: journey_priority_inputs/mappings/prioritizations). Applied on 3002 only.
- apps/api/priority.py (router + pure engine, rule suggested-order-1): checks = stage assessments + current required outcome requirements; gap->checks by stage rule + reviewer corrections (reason, append-only); effort low/medium/high/unknown (default unknown); prerequisites (gap/check, validated: workspace, self, missing, cycle; stale ones warn, don't block); order = ready before blocked, more distinct unresolved checks, effort low<medium<high<unknown, stable key; sent requests = Waiting. Saved versions (append-only) with input hash -> stale detection, explicit refresh (no carried override), reviewer override with reason.
- journey.py: gaps carry a structured target; draft_collection accepts prioritization_id, structured duplicate guard (409 with matches unless a reason is given), audit payload from_suggested_order. release_api/report: journey_priority_summary + inputs/mappings/prioritizations (last three reviewer/owner only).
- UI: apps/web/app/priority-panel.tsx inside Document journey 'Collection plan · suggested request order' (lazy-loaded on open); scoped .prio-* CSS.
- Tests (3002): unit 118 (9 new priority); priority_integration 7 groups; journey/provenance/improvement/case_watch integration pass; browser priority-check, journey-check, freshness, provenance, design-check pass; full release-check passes (one earlier run failed once on a 'Malformed value' datetime fill, passed on rerun, not diagnosed). Screenshots: artifacts/priority-screenshots/.
## Release prep 2026-10-14 (3002 only; 3001/3003 untouched; NOT deployed)
- Fix 1 (priority.py, priority-panel.tsx): vanished/unmatched prerequisite = state 'unmatched', still blocks (was 'stale', non-blocking). Kept as recorded on unrelated edits;
  removal/replacement needs owner/reviewer (existing writer check) + change_reason >=10 chars, stored in audit payload (removed_prerequisites); input revisions append-only; cycle/stale-hash unchanged. No migration.
- Fix 2: outcome check labels = name + '#'+first 8 of outcome_key (priority.py build_checks; document-journey.tsx list/legend). Check keys and ids unchanged.
- 3002 runs: unit test_priority 10 + test_journey 30; priority_integration 8, journey_integration 10, journey_provenance 3; browser priority-check, journey-check. User reported (not run by me) the full suites incl. release-check passing. Limit: removal reason lives in audit events.
- DEPLOY PLAN 3001 (NOT executed; needs approval; migrations 010-013 pending, all additive; head = commit of this section). Never touch 3003.
  1 bash scripts/verify-backup.sh ; bash scripts/live-fingerprint.sh > backups/fingerprint-pre-release.txt (read-only; ignores jobs/sessions, journey_*/source_* tables, 013 columns on case_watch_updates)
  2 for s in api worker web; do docker tag trialops-release-$s:latest trialops-release-$s:pre-source-17fe09b; done  (rollback images; compose.source-rollback.yaml)
  3 docker compose build api worker web ; docker compose up -d --no-deps --no-build --wait api worker web  (api start runs migrate.py -> 010-013)
  4 docker compose ps ; curl -fsSI localhost:3001/ ; bash scripts/live-fingerprint.sh | diff backups/fingerprint-pre-release.txt - (expect empty) ; SMOKE_EMAIL/SMOKE_PASSWORD/SMOKE_CASE bash scripts/live-smoke.sh
  Sources start empty on live; ingestion stays internal (not in web proxy).
  ROLLBACK (data kept, schema stays): a) bash scripts/rollback-source-events.sh (pauses sources, ids -> backups/rollback-paused-sources-*.txt, stops worker, fails queued/running source_event jobs; events stay 'received')
   b) docker compose -f compose.yaml -f compose.source-rollback.yaml up -d --no-deps --no-build --wait api worker web  (older: compose.journey-rollback.yaml, tag pre-journey-a3a13df, needs 010-012 only)
   c) Roll forward: start new images, then re-enable: while read w s; do psql ... "UPDATE source_connections SET status='enabled' WHERE workspace_id='$w' AND id='$s' AND status='paused'" </dev/null; done < file ; scan_sources re-queues kept events. Restore backup (scripts/restore.sh) only if data damaged.
  Rehearsed on 3002 only (old-code image from 17fe09b): queued+running source_event jobs failed, sources paused, old api/worker healthy on 13-migration DB, events untouched, roll-forward + re-enable OK.
## Source-event automation 2026-10-15 (3002 only, uncommitted; 3001/3003 untouched; also pending: both Overview walkthrough removals)
- Backup before migration: backups/test3002-pre-source-20261015-092917.dump (restored to temp DB: 138 cases/17 workspaces/12 migrations matched; temp DB dropped). Migration 013 (additive: source_connections/events/event_conflicts, automation_settings; jobs kind 'source_event'; case_watch_updates +source_event_id,+detail).
- apps/api/source_events.py: POST /sources/events (X-Source-Key, hash-stored, workspace bound to key), mock producer POST /sources/{id}/mock-event, owner settings (/sources, /status, /automation), scan_sources in worker loop, process_source_event (route exactly via journey identity/classify -> journey_exports -> journey/priority recompute -> case_watch_updates + one notification), reroute, review. worker.py dispatch; web: source-automation.tsx (Settings > Data policy, owner only), case-watch.tsx SourceUpdate.
- Results (3002): source_events_integration 13 groups; comparison script; real worker stop/start resumed 1 event once; unit 119; journey/provenance/priority/case_watch/improvement/release integration pass; browser source-check, watch/journey/priority/design-check, release-check pass. Screenshots artifacts/source-screenshots.
- Limits: mock adapters, push only (no pull polling/real vendor); ingestion endpoint not in web proxy (deployment decision); source_declared xref unused; bursts serialize per case, one unread notification. Also in this commit: Overview walkthrough removals, source-form alignment (Settings > Data policy; checked 1440/390).
