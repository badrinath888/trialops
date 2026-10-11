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
## Commands (project root)
- Test: docker compose -p trialops-release-test -f compose.yaml -f compose.release-test.yaml
  build web; same prefix up -d --no-deps --no-build --wait web.
- Browser: TEST_WEB_URL=http://localhost:3002 PLAYWRIGHT_MODULE=./node_modules/playwright
  CHROMIUM_PATH='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
  node tests/browser/visual-review.cjs (module resolved relative to test script).
- Live: docker compose up -d --no-deps --no-build --wait web after tested image tag.
- No migrations required; retain existing verified backups and old web image for rollback.
- Preserve all DBs/accounts/uploads/private files; never reset or send externally.
