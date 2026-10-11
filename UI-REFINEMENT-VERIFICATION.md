# Cohesive UI refinement — 2026-10-10

Scope: the approved graphite sidebar, warm ivory surfaces, restrained copper,
serif page headings and readable sans-serif body. Applied shared styles across
landing, sign-in/recovery/verification, Overview, Cases/intake/details, saved
investigations, Knowledge, Operational records, ROI, Feedback, Settings, guide
and restricted response pages. Referenced image attachments were unavailable
in this turn; implementation follows the supplied written design requirements.

Routine sections use spacing/dividers rather than nested cards. Dark bands are
reserved for Overview totals and case guidance. Buttons retain 44px minimum
height, visible keyboard focus and consistent spacing. Motion is restrained;
guided programmatic scrolling now honors reduced motion. My work displays five
initial items with every remaining action available through expansion. Current
counts, deadlines, checklist state and permissions still come from existing APIs.
No backend, schema, approval, resolution, citation, external-link security or
inference changes. Corrected stale recovery wording in sign-in and Settings.

## Actual verification

- Final isolated web production build passed compilation, TypeScript checks and
  static generation. Only the web service was built/recreated.
- `visual-review.cjs`: 54 populated/public states at 1440/390px; 4,575 computed
  text-contrast samples; zero overflow, text-size, control-size, contrast or
  page-error failures. Includes all routes, finding tabs, mobile navigation,
  short-height sidebar scrolling, preview/Escape/focus return and preferences.
- `design-check.cjs`: 29 states pass: recovery/reset/verification/unavailable
  response, actual zero-match case search, empty queue/library/history/records/
  ROI/feedback, long titles/all personal items, loading/error, retained/discarded
  unsaved procedure, dialog focus loop and reduced-motion guided scrolling.
  Some empty/loading/error/long-title states use explicit UI response fixtures;
  these test display behavior without pretending fixture counts are saved data.
- `five-check.cjs`: 18 desktop/narrow states pass: populated directory, blockers,
  acknowledged handover, duplicate reuse, history/Overview, local-mail recovery,
  email verification/password reset and exports. Exact recorded fresh accounts
  removed with the existing guarded cleanup helper; existing accounts retained.
- `user-workflow-check.cjs`: 18 desktop/narrow states pass: real personal queue,
  versioned guidance, clipboard link, restricted anonymous submission, honest
  human consideration, saved current evidence/checks and separate resolution;
  token-safe JSON and PDF download passed, zero page errors.
- Screenshot contact sheets and readable case/authentication crops inspected;
  empty/public/state and populated continuity/directory screens inspected.
- After the Overview reorder (summary band above My work; Needs action/Waiting tabs),
  rebuilt test web on 3002: design-check 29 states, visual-review 54 pages + 9
  interactions with no issues, user-workflow-check passed, release-check 16 states,
  0 errors, 5 interactions (matches earlier regression). Overview screenshot inspected.

## Deployment / preservation

- Web-only deploy to port 3001 completed 2026-10-10 after the checks above. No
  migrations; API, worker and database containers were not restarted.
- Preservation limits: no full pre-edit record fingerprint of either database was
  found in /private/tmp (only an empty external-response baseline and Oct 8 service
  IDs), so earlier preservation is NOT claimed. A fingerprint taken immediately
  before deploy (users, workspaces, memberships, cases, runs, knowledge, operations,
  case_events; private file) matched after deploy for the live DB. The test DB
  changed only through browser tests run against it. Environment/secrets/uploads
  remain outside Git.
- Live check: / and /sign-in return 200, web healthy, bundle contains the new tabs.
  Browser suites were not run on 3001 because they create sample workspaces.
- Exact previous live web image retained as
  `trialops-release-web:pre-visual-9fe1132`.
- Web-only rollback, from project root:
  `docker compose -f compose.yaml -f compose.ui-rollback.yaml up -d --no-deps --no-build --wait web`
  This leaves API/worker/database services, schema and stored history intact.
- Screenshots, generated exports, raw logs and preservation evidence stay in
  ignored `artifacts/ui-refinement` or private temporary files.

## Coverage limits

Chromium at desktop/narrow widths, plus short-height sidebar and keyboard checks;
not an exhaustive browser/device/screen-reader audit. Computed contrast checks
skip uncertain translucent/gradient backgrounds and supplement visual inspection.
Backend/model-quality suites were not repeated for a presentation-only change;
existing workflow browser regressions exercise affected controls. Export rendering
code is unchanged; the prior full PDF visual verification remains applicable.
No external test emails/messages, paid inference or public deployment.
