# Five-feature verification — 2026-10-10

Implemented on top of cc838b7 without restarting prior feature work.

- 53 unit tests passed, including deterministic duplicate identifiers, interval
  union and disabled/bounded email delivery.
- Seven focused integration groups passed: current workspace/role validation;
  directory scope/archive/idempotence; multiple blockers/history/reminders;
  duplicate warning/reasoned override/different evidence/concurrent replay;
  handover owner retention, concurrent acceptance and single audit attribution;
  decline/cancel/revoked membership; token-free exports; local Mailpit delivery,
  hashed purpose/expiry/single-use tokens, generic recovery, rate limits,
  concurrent consumption, old-password rejection and all-session revocation.
- Existing15 integration groups, release10 groups and boundary5 groups passed.
  Includes actual worker evaluation, immutable evidence/history and lost leases.
- Production API/worker/web images built successfully; final web build includes
  the verified same-page verification/reset-link navigation fix.
- Populated desktop1440 and narrow390 five-feature browser journey passed18
  captured states with zero page errors and no horizontal overflow. Exercised
  directory, blockers, accepted handover, duplicate reuse, clearing/history,
  overview, generic recovery, local mail verification/reset and JSON/PDF exports.
- JSON assertions confirmed accepted handover and cleared blocker history.
  Complete13-page case PDF rendered and visually inspected; new history and
  elapsed waiting-time sections are present with readable pagination.
- Broader prior-feature browser regression initially hit the real session rate
  limit; pacing repeated case navigation fixed the test. Rerun passed16 states,
  including activation, separate resolution/reopening, imports, monitoring,
  procedure reassessment and actual worker evaluation; limits unchanged.

Preservation checks exclude only additive columns from old-row serialization and
compare original permanent workspace/account/case/investigation/evidence/request/
assessment/audit records. Disposable browser accounts are identified by exact
recorded IDs plus sample.invalid address and creation-time guards before cleanup.
No database reset is used. Private environment/secret/upload file SHA256 values
are kept privately and compared without publishing their contents.

Test backup restored before test migrations:
`backups/trialops-five-test-verified-20261010-104805-31125.dump`.
Fresh live backup restored into a separate verification database before live
migrations, with retained SHA256:
`backups/trialops-verified-20261010-110431-38460.dump`.
Rollback application images retained as pre-five-cc838b7. Live004–006 applied;
only api/worker/web updated from tested images. Database service/volumes preserved.
Live health and final workflow/preservation outcome: see final checkpoint below.

Coverage limits: Chromium at two viewport sizes, not every device/browser or a
formal screen-reader audit. Local catcher establishes local email behavior only;
real delivery is unconfigured on live3001. Duplicate detection is bounded lexical
matching, not semantic equivalence. SMTP attempts/socket timeouts are bounded;
external DNS/inbox delivery and provider-specific policies are not evaluated.
No new model-quality claims or model calls are introduced by these five features.

## Final live verification
Live api/db/worker/web are healthy. The integrated five-feature browser journey
passed14 desktop/narrow states with zero page errors; external email remained
unconfigured. Exact disposable live fixtures were removed afterwards. Final
original-record fingerprints match both live/test databases, including accounts,
memberships, cases, saved investigations, knowledge, observations, audit history,
requests, checks, frozen evidence and assessments. Original private-file hashes
match. No secrets, tokens, backup dumps or generated screenshots are committed.
