# User-workflow release verification — 2026-10-10
Base b7f886c; prior releases preserved. Only requested integrated scope added.

## Completed checks
- 57 unit tests passed, including current human verification versus historical
 snapshots, role/closed-case guidance, and malformed/whitespace/oversized input.
- 6 expanded workflow integration groups passed: personal ownership/deadline/check/
 handover/blocker accuracy; workspace/role isolation; stale next-step rejection;
 opaque hashed tokens and minimal context; mutation-free GET; expiry/revocation;
 current workspace policy; trimmed bounds/forged fields, invalid text and pasted
 access secrets; same-body concurrent
 submissions produce one response; competing bodies rejected; truthful unverified
 provenance; existing reminder channel; human clarification/consideration with
 versioned audit; withdrawn requests rejected in guidance/personal queues too; token/contact-safe
 case exports.
- The overdue-check test exposed a wrong checklist owner lookup; corrected to case
 ownership. Short text validation exposed an inherited annotated-type minimum
 override; corrected at the new public boundary and covered directly.
- Existing15 integration, release10 integration and five-feature7 groups passed.
 Prior-feature browser regression passed16 states, including separate reopening,
 imports, monitoring preparation, procedure reassessment and worker evaluation.
 Existing5 boundary groups passed, including lost worker leases and interruptions.
- Production API/worker/web builds passed, including final queue/history/read-retry
 refinements. Expanded focused checks pass, including310 unrelated earlier-deadline
 cases that cannot hide the user’s personal work.
- Populated Chromium journey passed18 desktop1440/narrow390 states with zero page
 errors/overflow: personal queue, explicit investigation, human approval/check
 activation, request creation, actual clipboard copy, restricted anonymous view,
 text submission, pending human review, acceptance while case remains open,
 independent current human observation/checks, separate manual resolution.
 Anonymous visitor could not access case API; fragment removed; no token in HTTP
 URLs/referrers. Literal malicious script text did not execute.
- JSON exports assert accepted response history, no access secret/token_hash or
 recipient address. Complete20-page PDF rendered/visually inspected; text checks
 confirmed honest provenance/human review and no recipient address/token hash.
- Original permanent-record fingerprints matched both preserved databases after
 test migrations/checks and exact fresh browser-sample cleanup.

## Backups and deployment
Fresh isolated backup restored into a separate verification database before007:
`backups/trialops-verified-20261010-112050-45646.dump`.
Fresh live backup restored into a separate verification database before007:
`backups/trialops-verified-20261010-185338-6065.dump`; SHA256 verified.
Current live images retained as pre-user-workflow-b7f886c. Migration007 applied
locally; only api/worker/web updated, with final refinements affecting API/web only.
All live services healthy. Full original rows in both databases (including prior
contact fields and knowledge chunks) and private-file fingerprints matched after
migration. Final live workflow outcome is recorded below after fixture cleanup.

## Coverage limits
Chromium at two viewport widths, not all browsers/devices or a formal screen-reader
certification. Restricted responses are text-only and bearer possession is not
verified identity/truth. Public GET rate counters are process-local; POST counters
are shared. Existing reminder scan frequency/preferences govern delivery latency.
Queue bounds and volatile drafts are documented in USER-WORKFLOW-RELEASE.md.
No new inference path or model-quality claim is introduced. No external sending,
public deployment, account resets or database resets are used.

## Final live outcome
The full live3001 journey passed18 desktop/narrow states, zero page errors/overflow,
including an external arrival shown on returning focus without page reload, honest
human consideration, independently verified checks and separate manual resolution.
Live api/db/worker/web are healthy. Exact fresh expiring browser samples were removed
using guarded IDs; all original full-row fingerprints match both databases,
including accounts, prior contact fields, saved investigations, knowledge chunks,
requests, evidence, assessments and audit history. Original private-file hashes
match. No external sending, public deployment or reset occurred. Backup dump/SHA,
private invariants and generated exports/screenshots remain excluded from Git.
