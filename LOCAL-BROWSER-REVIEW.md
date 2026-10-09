# Local Playwright UI review

Reviewed http://localhost:3001 using the project's locked Playwright 1.62.1 dependency and local headless Chromium. `npm ci` installed the missing test dependencies; Chromium already launched successfully, so a browser download was unnecessary.

## Data preservation and deployment

Each run used a fresh browser context and the app's “Explore a sample case” flow. These workspaces are marked as samples and expire after 24 hours. All test writes (cases, investigations, reviews, resolution/reopening, procedures, snapshots, feedback, study/site records and ROI scenarios) were scoped to those samples. Existing accounts were never signed into. No database reset, volume removal, migration, or cleanup was performed. Synthetic sample records remain until the application's normal expiry handling.

Existing working-tree changes were retained. This review adds two CSS corrections, a specific selector for the duplicated landing CTA in `check.cjs`, and a reusable `visual-review.cjs` script exposed as `npm run test:visual`.

Only `web` was built and replaced, using `docker compose build web` and `docker compose up -d --no-deps --wait web`. It became healthy. API, database and worker container IDs were compared before and after and stayed identical.

## Verified UI fixes

| Issue | Evidence | Fix |
| --- | --- | --- |
| Landing “Built into the workflow” badge had white text on a pale background | Visually illegible in the original screenshot; computed text contrast 1.16:1 | Give the badge dark text while keeping the surrounding dark card's white text |
| Case-detail priority badge background was overridden by a general context-chip rule | Computed medium-priority text contrast 4.46:1; pale beige appearance differed from Cases | Exclude `.badge` from the general context-chip selector so semantic badges retain their intended background |

The light copper asterisk is part of the wordmark/logo and was excluded from text-contrast assertions. No brand redesign was performed.

## Visual inspection

Inspected full-page screenshots and contact sheets of landing, sign-in, registration, guide, overview, Cases, case detail, Submit issue, Knowledge, Investigations, Operational records, ROI, Feedback and Settings at 1440px and 390px widths. All four Settings sections were inspected. Additional screenshots cover procedure detail, populated findings tabs, saved ROI content, preview modal, expanded mobile navigation and a 620px-high desktop sidebar. The standalone saved-investigation page is included in the final automated capture.

Typography is readable, the form fields and action buttons share consistent sizing, and desktop spacing remains compact. Narrow layouts stack forms/cards and wrap actions and settings choices. Cases and Knowledge tables intentionally scroll horizontally within their own containers; the page itself does not overflow. Sidebar navigation scrolls independently at short desktop heights, and mobile navigation exposes all nine main destinations. The two verified contrast defects above are corrected in the rebuilt app.

Artifacts: `artifacts/ui-review/` contains before screenshots/contact sheets. `artifacts/ui-review/final/` contains the final screenshots and `computed-review.json`; its `pages` array identifies the states measured by the final run. `artifacts/ui-review/final-baseline/` contains the existing suite's screenshots and synthetic PDF/JSON exports.

Final computed review passed for 54 captured states, with 3839 measured text instances and no reported contrast, text-size, control-size, page-overflow or uncaught browser-error failures.

## Automated checks

- Existing `tests/browser/check.cjs`: passed against the rebuilt web service. Exercises sample onboarding, investigation, approval, PDF download, resolution/reopening, insufficient-evidence rejection, procedure upload/extraction, classification and intake, feedback, workspace export, study/site creation, responsive overview at 1440/1024/768/390px, mobile navigation, no uncaught browser errors, and cross-origin write blocking.
- `visual-review.cjs`: measures rendered text contrast on solid backgrounds, text size, control size and page overflow at desktop/narrow widths. It also exercises findings-tab keyboard navigation, investigation/approval, ROI confirmation/save, invalid and valid snapshot import, keyboard table scrolling, preview Escape/focus return, menu Escape/focus return, preference persistence, empty intake validation and short-height sidebar access.
- Production Next.js build: compilation, TypeScript and route generation passed.
- JavaScript syntax checks and `git diff --check`: passed.

Reproduce from the repository root:

```sh
npm ci --prefix tests/browser
TEST_SCREENSHOT_DIR="$PWD/artifacts/ui-review/recheck" npm run test:visual --prefix tests/browser
TEST_SCREENSHOT_DIR="$PWD/artifacts/ui-review/recheck-baseline" npm test --prefix tests/browser
```

## Limits and test-harness corrections

These are Chromium desktop screenshots at simulated viewport widths, not Safari/Firefox, real touch devices or a screen-reader audit. Permanent-account sign-in, invitation acceptance, multi-user role behavior and permanent-account procedure editing/archive/restore were not tested; the existing permanent-account suites were intentionally not run. Not every hover/focus/disabled state or every disclosure/content combination was captured. Contrast measurements skip gradients and opacity effects, and do not certify complete WCAG compliance or measure all non-text borders/icons.

Local browser execution succeeded. Initial test-harness errors were corrected: the landing CTA selector matched two buttons, the snapshot-error selector also matched Next.js's route announcer, and saving an example snapshot needed to wait for its asynchronous load. These were test selection/timing failures, not findings against existing account data.
