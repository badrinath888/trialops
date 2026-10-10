# Five-feature local release

## Where to find it
- Sign-in → Forgot password; Settings → Email verification. Existing login access
  does not require verification, including accounts created before migration.
- Case → Evidence & follow-up → Case handover & blockers. Ownership changes only
  after the named current member accepts. Decline/cancel retain the owner.
- Information requests warn before creating overlapping open evidence requests;
  reuse the existing request or record an override reason. Draft editing supports
  contacts and override reasons too. Nothing is sent automatically.
- Overview → Waiting on follow-up lists active blockers and relevant handovers.
- Settings → Support contact directory; relevant contacts appear in case/request
  forms. Archive preserves historical references. Contacts never grant access.
- Case PDF/JSON exports include attributed handover and blocker history, frozen
  summaries and elapsed waiting time. Authentication tokens are excluded.

## Configuration and security
SMTP_HOST and MAIL_FROM enable email delivery. Optional SMTP_PORT (587),
SMTP_STARTTLS (true), SMTP_SSL (false), SMTP_USER and SMTP_PASSWORD configure
transport. APP_PUBLIC_URL must be the trusted installation origin. Keep credentials
in existing private environment configuration, never in Git. Live delivery remains
unconfigured unless explicitly configured; recovery then returns the same generic
response but no mail is sent. Verification status never gates existing account access.
Test compose uses internal Mailpit SMTP1025 and loopback-only UI localhost:8026.
All test recipients use sample.invalid; no external test mail is authorized.

Delivery is synchronous, at most two attempts with 5-second socket timeouts.
Raw tokens exist only in memory and email; database stores hashes, purpose, expiry
and consumption time. Reset tokens expire after 30 minutes, verification after
24 hours. Reissue invalidates prior unused tokens of that purpose. User-row locking
serializes consumption; password reset revokes every session. Rate limits use the
existing shared limiter. Links use fragments stripped immediately by the client.
Use trusted TLS email delivery and HTTPS if configuring a non-local installation.

Every workflow is workspace scoped and rechecks current membership and role.
Owner/reviewer roles edit contacts, blockers and initiate handovers; only the named
recipient acknowledges, with sender/owner cancellation. Case locking and a unique
pending-handover index prevent concurrent transfers. Direct reassignment is rejected
while a handover is pending. Audit attribution and original owner are retained.
Contact references validate study/site scope; archive prevents new references.
Retrieved/user text remains data; these features introduce no model calls or tools.

Duplicate matching is deterministic normalized word overlap (85%) with matching
identifiers, within the same workspace/study/site and open draft/requested records.
It is a warning, not semantic proof: paraphrases or unusual identifiers may be missed.
The review examines up to 200 recent open requests. Directory/blocker records are
bounded at 200; overview queues return up to 100 entries. Concurrent replay of the
same submission ID returns the original result. Different evidence remains valid.
Blocked duration unions overlapping intervals and stops at resolution/current time;
it is elapsed waiting time, never added to human effort. Responsible member/contact
and mandatory follow-up support the existing deadline reminder preferences.

## Migration and rollback
Migrations004–006 are additive. Preserve checksums; do not edit applied migrations.
004 adds workflow/auth tables and nullable verification/contact fields; 005 adds
separate directory audit; 006 makes optional contact references safe during workspace
cleanup. No existing login, password, session or evidence record is rewritten.

Before deploying, stop only api/worker/web writers, run scripts/verify-backup.sh,
retain its dump/SHA and successful separate-database restore log, and compare the
original permanent-record fingerprints. Never restore over either database for a test.
Tag current application images pre-five-cc838b7 before updating; migrate with the
verified API image and update only api/worker/web. Keep database/upload volumes.
If health, authorization or preservation checks fail, stop affected writers and run:
`docker compose -f compose.yaml -f compose.five-rollback.yaml up -d --no-deps --no-build --wait api worker web`.
The rollback keeps additive schema and workflow history but hides these new controls.
A database restore is an explicit recovery operation, not normal application rollback.
Do not use down -v or reset either installation.

## Verification
Actual final results and deployment details are recorded in DEV-CHECKPOINT.md and
FIVE-FEATURE-VERIFICATION.md. Automated checks do not establish deliverability to
real external inboxes, screen-reader compatibility, or exhaustive browser/device
coverage. Local mail catcher verifies delivery and browser token consumption only.
