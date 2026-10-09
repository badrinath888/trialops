# Frontend usability review · October 8, 2026

This review modifies the existing TrialOps frontend directly. It preserves the Graphite & Copper theme and uses existing React components, CSS, native disclosures, and native radio controls. No dependencies were added.

## Source and deployment comparison

Before frontend edits, an unmodified `docker compose build web` reused the cached source-copy and production-build layers. The source-built image and running web container both had build ID `Ik9P4_PWEvkf9vUJmY6RM` and compiled CSS SHA-256 `60072b19274a391505dd580d3ae422ea3655a3e0e3eadbd4de118f13922c1257`.

The current 1.4.1 Preferences radio controls were already deployed. They were not replaced, and their persistence behavior was not changed. Their existing opaque white/selected warm backgrounds remain. Safari's actual rendering of the reported translucency could not be inspected.

Neither this directory nor its parent had a Git repository. Local baseline commit `8d96ff8` records the application before frontend edits. `.gitignore` excludes private environment files, secrets, backups, uploads, exports, dependency/build caches, and generated previews/screenshots. Existing files were retained.

## Page review and manual acceptance checklist

All pages below were reviewed in source. **None has been visually or interactively verified in a browser in this session:** the browser runtime reported no available browsers. HTTP responses do not verify React hydration, authenticated page content, computed styles, layout, or keyboard behavior.

| Page | Changes / retained behavior | Inspect manually on your Mac |
| --- | --- | --- |
| Landing | Removed decorative preview dots, redundant sample wording and offset preview shadow; tighter sections; retained useful interactive workflow demo. | Sample tabs with arrows/Home/End, contrast, action wrapping at narrow widths. |
| Sign-in / registration | Solid form surface, compact story spacing, shorter registration wording; consistent inputs and buttons. | Both account modes, browser autofill/password appearance, error text, tab keyboard controls. |
| Overview | Compact metrics and rows; shorter introduction; existing attention categories and previews retained. | Counts, long titles, empty queues, preview Escape and focus return. |
| Cases / case detail | Shared solid controls and table spacing; keyboard-focusable scrolling tables; preserved filters, previews, approvals and separate manual resolution. | Search/pagination, horizontal table scrolling using keyboard, modal focus, background-job status, resolution confirmation. |
| Submit issue | Removed repeated right-side progress guidance; one-column form with readable text; classification review unchanged. | Dependent study/site selections, classification suggestion, create-case action and validation. |
| Knowledge | Compact keyboard-accessible table; plain search-readiness wording; procedure inspection/editing and extraction review retained. | Upload extraction, read-before-edit flow, archive/restore, discard confirmation, table scrolling. |
| Investigations / saved findings | Added loading/error states during filtering and disabled pagination while loading; main link to choose a case; list no longer repeats model/run IDs. Procedures collapse by default; technical identifiers remain in Activity disclosures. Exports are secondary to review. | History filters, loading/failure states, findings tabs with arrows/Home/End, procedure expansion, PDF/JSON downloads, review notes. |
| Operational records | Main import link; readable saved record fields with technical JSON nested behind a disclosure; smaller JSON editor. | Import-link scrolling, record disclosures, long field values, validation errors. |
| ROI | Consistent readable numeric inputs and preview; save progress text; run reference expandable. Scenario assumptions, negative values and required confirmation retained. | Numeric calculations, negative estimates, confirmation and save state. |
| Feedback | Solid selectable rating surfaces, visible focus, consistent submit button and busy announcement. | Rating keyboard selection, contrast, submission validation and success message. |
| Settings | Existing Preferences controls retained; shorter description; study/site catalog collapsed initially; shared solid controls and section styling. | **Preferences on Safari**, selected/unselected states, arrow-key radio navigation, save/persistence, all team/catalog/policy sections. |
| Guide | Shared readable controls, compact spacing and disclosure styles apply. | Contents links, disclosures and data-policy anchor. |

Across workspace pages, active navigation links announce the current page, route changes focus the main content, mobile Menu controls identify their navigation region, and Escape inside an expanded mobile menu returns focus to Menu. Desktop sidebar uses viewport height, independent scrolling, and non-shrinking children. Check these at a short desktop window (about 620px high) and at mobile width. These are source changes, not completed interactive tests.

## Shared presentation

- Body and controls remain 16px; table helper text remains at least 15px. Buttons retain a 44px minimum height.
- Secondary buttons, inputs, options, disabled controls, rating choices and sign-in panels use solid backgrounds. Disabled text no longer fades with opacity.
- Graphite/copper focus indicators, table row focus highlighting, short color/border/box-shadow transitions, and busy cursors provide subtle feedback.
- Reduced-motion overrides remain in place. No simulated investigation progress was added.
- Procedures, escalation drafts, historical records, technical JSON and run identifiers remain accessible through tabs/disclosures. Source procedure text was not rewritten.

## Executed checks

- Final Docker production web build: passed compilation, TypeScript, and Next.js route generation.
- `docker compose exec -T api python -m unittest discover -s tests -p 'test_*.py' -v`: **27 tests passed**. These exercise deterministic evidence/policy/upload/report behavior without modifying the database.
- Source palette WCAG calculations: 10 sampled text pairs met 4.5:1 (minimum 5.07:1); input border and two focus pairs met 3:1 (minimum 3.34:1). These calculations use source colors, not computed styles or a complete rendered-page contrast audit.
- `git diff --check`: passed.
- Compared backend, schema, Compose and Next.js API proxy with baseline: no changes.
- Replaced only web using `docker compose up -d --no-deps --wait web`; web became healthy. API, database and worker retained their container IDs and remained healthy.
- Read-only HTTP smoke checks: landing, sign-in, guide and all nine workspace routes returned 200; `/api/health` returned 200; unauthenticated `/api/auth/me` returned 401.

Browser baseline, permanent-account UX and desktop workflow suites were **not run**, because browser access is unavailable. API integration tests were not rerun for this frontend-only change. Existing release results in TEST-REPORT.md are historical, not evidence for this review.

## Load the changes

The web service has already been rebuilt and restarted. Open http://localhost:3001 and press **Cmd + Shift + R**. Inspect the pages in the table at desktop and narrow widths, especially Settings > Preferences and sidebar scrolling. With macOS Reduce Motion enabled, check that transitions are suppressed.

Future frontend edits can be loaded with `docker compose build web` followed by `docker compose up -d --no-deps --wait web`. No database volume removal, initialization, reset, or source updater is needed. The original SHA256SUMS remains the historical release manifest; the customized source now differs from that package.

## Follow-up: case recognition and search

Case titles are now prominent, with compact copper-tinted chips showing the original IDs in Cases, recent Overview cases, and previews. Cases includes the latest investigation's review status separately from priority; assignment and follow-up remain visible. IDs and stored case titles were not rewritten.

Search accepts `1`, `case 1`, and `CASE-1` as equivalent exact searches for CASE-1, avoiding matches against CASE-10 or numbers in study/site IDs. Text searches for titles, full study/site IDs, and custom case IDs retain their existing behavior. Status, priority, personal views, pagination and workspace scope still apply.

This follow-up adds read-only case-list query behavior in the API, so API and web require rebuilding; it supersedes the frontend-only deployment scope above for this specific feature. No database migration or worker change is involved. Approval/resolution endpoints and audit-writing behavior remain unchanged.

Checks executed: production web build and TypeScript passed; all 30 deterministic tests passed (including three new query regressions); real PostgreSQL read-only checks passed for numeric aliases, workspace scope, latest review status and filtered pagination. No records were written by these checks. Browser visual/interaction verification remains unavailable; manually inspect Cases search, status labels, long IDs/titles and narrow-width table scrolling.

## Follow-up: shared form alignment

The ROI and case-resolution checkbox misalignment came from native checkboxes inheriting text-input minimum height and padding. Shared checkbox rules now reset those dimensions, and confirmation labels use an 18px checkbox column aligned to the first text line. Whole labels retain a 44px minimum interaction height. Paired form labels align their controls at the bottom even when captions wrap; direct form helper notes are block-level.

Production build and TypeScript passed. Browser test scripts passed JavaScript syntax checks, and the desktop workflow suite now includes checkbox alignment assertions at 1440, 1024, 768 and 390px. These new browser assertions have **not been executed**: the browser connection again returned an empty list. A full rendered-page and keyboard review is pending a browser connection; source checks do not substitute for it.
