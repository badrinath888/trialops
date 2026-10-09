# TrialOps 1.4.1 readability verification

This targeted frontend correction replaces the two native preference menus with opaque, labelled radio choices. Production build and TypeScript passed. The desktop workflow browser suite passed with added radio keyboard checks, persistence/sign-in destination checks, and opaque dark-text/44px-label checks at 1440, 1024, 768, and 390px. Settings screenshots inspected. No backend or schema behavior changed.

The preceding 1.4 release passed 27 unit tests and 15 integration groups both during preparation and in the user's native Docker/Ollama installation. The updater repeats the native checks before cleanup. Existing data and preferences are preserved.

# TrialOps 1.4 desktop workflow verification

## Checks for this release

- Optimized Next.js production build, TypeScript, and route generation.
- 27 investigation, operational-policy, upload, and PDF-report unit tests.
- 15 API integration groups: accounts/workspace isolation, catalogs, attention queue, new case views and pagination, real worker/MCP calls, review/resolution/reopening, abstention, immutable knowledge, imports, assignments, notes, ROI, feedback, export, worker recovery, invitations, and permissions.
- Browser baseline: sample onboarding, investigation, PDF download, approval, manual resolve/reopen, unsupported rejection, extraction, reviewed classification, intake, feedback, export, catalogs, responsive navigation, and cross-origin write protection.
- Permanent-account UX walkthrough: wrong-password recovery, sign-out/sign-in, forms, search/filtering, notes, deadlines, navigation during background investigation, queue categories, findings tabs and keyboard controls, ROI confirmation, snapshot validation, procedure edit/archive/restore, and invitations.
- New desktop workflow checks: requested previews, focus wrap, Escape/return focus, URL and pagination persistence, saved filters, inspection before editing, unsaved-edit confirmation, account-scoped preferences, and preferred sign-in destination.
- All nine workspace routes checked at 1440, 1024, 768, and 390px: no page horizontal overflow, no visible text below 15px, and visible buttons at least 44px with a 1px measurement tolerance. Desktop sidebar sign-out checked at 620px height. Reduced-motion preference checked.
- Screenshots of Overview, Cases, Investigation, Knowledge, and Settings inspected. Compact table/list spacing does not shrink text.
- Source-updater preservation/security fixtures, shell syntax, SHA-256 manifest, and ZIP integrity checks.

The 1.4 checks below passed while preparing that release; the focused 1.4.1 checks are described above. Saved filters and display preferences use per-account browser storage; they do not synchronize across devices.

## Execution environment and installation

Browser and API integration checks here use the QA-only PGlite PostgreSQL/vector adapter with the real API, worker, MCP tools, and procedure mode. The delivered runtime remains Docker PostgreSQL 16 and psycopg. Native Ollama/Docker checks execute on your Mac during the update; this is not a claim that version 1.4 is already installed there. QA adapters, sessions, databases, secrets, caches, and dependencies are excluded from the ZIP.

The updater backs up the database and replaced source, rebuilds services, waits for health checks, runs 27 unit tests and the full 15-group native integration suite, then cleans known disposable files. Accounts, database, credentials, uploads, Git history, unknown user files, and backups are preserved. Public HTTPS hosting remains a separate deployment.
