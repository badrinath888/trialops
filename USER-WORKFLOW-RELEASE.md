# My work today + Guided next step + External responses

## Locations and walkthrough
Overview → My work today separates actions from waiting. Every row explains its
assignment/deadline and opens the relevant case checks, requests or continuity
panel. Existing team queues remain in place; no second notification channel.

Case → Next step shows a deterministic recommendation and other available
controls. It refreshes after mutations/job completion and rechecks a workflow
fingerprint before opening an action. It never approves findings, confirms
observations or resolves a case. Existing resolution guards remain authoritative:
approved supported investigation, reviewed active checks, current-cycle human
observation, verification time and explicit exceptions/rationale.

Case → Information requests → saved request → External response link & review.
An owner/reviewer selects an active relevant directory contact, marks the request
requested, and explicitly creates/copies the restricted link. Nothing is sent.
The visitor sees only the frozen title/items and explicitly shared clarification.
They enter text, which remains pending human consideration. A reviewer records a
reason and accepts for consideration or requests clarification. Clarification
requires creating/sharing a new link; internal review reasons are not disclosed.
Acceptance records received input, but never verifies truth, completes checks or
resolves the case. Independently verify current evidence, complete the necessary
checks, and record resolution separately. Response/reminder history is retained.

Settings → External response links lets the workspace owner disable the portal.
Directory contacts do not receive account permissions. This release is text-only;
no attachment capability was added to the restricted trust boundary.

## Security and limits
- Each link has a48-byte random opaque secret; only SHA256 is stored. Link creation
  returns the fragment once; list/history endpoints never return secrets/hashes.
- Links default to72 hours, configurable1–336 hours, and are revocable. Creating
  a replacement revokes previous links. Workspace expiry can end access sooner.
  At most30 links/responses per request.
- Fragment URLs keep secrets out of HTTP paths/query/referrers. The response page
  strips the fragment immediately, uses memory only, no analytics/third-party
  assets, same-origin CSP, no-referrer/no-store headers. Token travels only in a
  dedicated request header through the existing private server proxy. API access
  logging stays disabled; tokens are excluded from audit payloads and exports.
- The token grants access to one frozen question/submission, not an account or
  verified identity. Honest attribution: “External link holder; identity not
  verified.” No internal notes, case details or workspace navigation are exposed.
- GET views only read business data and do not consume tokens. Public view budgets
  are30/minute per token and IP, in bounded process memory4096 keys; deployments
  with multiple API processes would need shared read-rate storage. Submission
  limits use existing shared database counters:20/IP and10/token per15 minutes.
- Submissions are trimmed10–4000 characters; schema and API enforce bounds.
  Unsupported NUL/surrogate text and pasted response-link secrets are rejected
  before storage. Model
  input is never created from this workflow. Untrusted text renders as text and
  is escaped in PDF reports. No shell, fetching, sending or model calls are added.
- Case/request/link locks and a unique response-per-link constraint serialize
  retries/concurrent submission. Same submission ID/body returns the prior result;
  a competing body is rejected. Current expiry/revocation/status/workspace expiry
  and policy are checked under transaction locks; policy changes serialize with
  submission even if a policy row did not exist. Withdrawn/received/resolved
  requests fail closed. Reopening does not revive received/withdrawn requests.
- Current member roles are rechecked for creation/revocation/review. Owner/reviewer
  roles review external content. Audits record member attribution and external
  provenance separately. Existing notification preferences/scanner deliver review
  reminders; this follows the configured scan interval, not instant delivery.
- Personal ownership/responsibility is filtered before bounds; unrelated team
  records cannot displace personal work. Queue scans up to300 relevant open
  cases/checklists/requests/blockers and100
  handovers. It shows real stored deadlines and case ownership for checklists.
  Request panes refresh on returning focus or opening the guided review action.
  Withdrawn/received requests no longer offer pending review actions. Guidance is
  advisory; other valid actions remain accessible. Stale actions are
  rejected and refreshed. Browser text drafts remain in component state across
  errors, but are not persisted across reload/navigation for privacy.
- Exports include responses, provenance and human decisions, excluding access
  secrets/hashes and recipient contact details from case PDF/JSON packages.

## Migration/deployment/rollback
Migration007 is additive: portal policy flag, restricted link hashes and response
history. Existing tables, accounts, requests, evidence and audit rows are retained.
Do not edit the checksum of an applied migration. Test first on preserved3002.
Before live migration, stop api/worker/web writers and run scripts/verify-backup.sh.
It restores the fresh dump into a separate verification database, never over live.
Keep the dump/SHA and successful log. Compare original permanent-record fingerprints
and private-file hashes; keep database/upload volumes and all existing backups.

Retain current application images as pre-user-workflow-b7f886c. Use tested images,
run `docker compose run --rm --no-deps api python migrate.py`, then update only
`docker compose up -d --no-deps --no-build --wait api worker web`.
If health, authorization or preservation checks fail, stop affected writers and:
`docker compose -f compose.yaml -f compose.user-workflow-rollback.yaml up -d --no-deps --no-build --wait api worker web`.
Rollback keeps additive schema/history but hides new controls. Revoke outstanding
links or disable workspace response policy before rollback if they are no longer
wanted. Database restore is an explicit recovery operation, not normal rollback.
Never down -v/reset either database. Deployment remains local3001 only.

Actual verification/deployment results: USER-WORKFLOW-VERIFICATION.md.
