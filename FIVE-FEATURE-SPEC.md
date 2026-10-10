# Five-feature TrialOps release

Base: cc838b7. Preserve the fourteen-feature and connected-assessment releases.
Live: localhost:3001. Isolated test: localhost:3002.

1. Password recovery and email verification: expiring, single-use, purpose-specific
   tokens stored as hashes; generic recovery responses; rate limits; revoke all
   sessions after reset. Configurable email delivery with bounded retries. Test
   through a local mail catcher only. Preserve existing account access during
   migration and report whether real email delivery is configured.
2. Case handover with acknowledgment: concise outstanding checks, requests,
   blockers and deadlines. Accept, decline, cancel; retain current owner until an
   eligible recipient accepts. Validate current membership/permissions, concurrent
   acceptance and attributed audit events.
3. Duplicate-request warning: deterministic same-evidence matching against open
   requests, explain matches, reuse existing request or proceed with a reason.
   Preserve genuinely different requests and prevent duplicate submissions. No LLM.
4. Blocker tracking: multiple waiting-on records with responsible person/contact,
   reason, start time, follow-up deadline, clearing and history. Case/overview queues.
   Blocked duration is separate from human effort; union overlapping intervals.
5. Support contact directory: workspace contacts with optional study/site, support
   category, primary/backup contact and escalation route. Authorized editing/archive;
   relevant contacts in case/request workflows. Contacts grant no account permissions
   and send nothing automatically.

Integration: reuse assignment, requests, reminders, auth and audit; graphite/copper,
compact/readable controls; server-side workspace/role isolation; handover/blocker
history in exports, no authentication tokens. Preserve both databases/accounts,
secrets/uploads/backups. Implement/test on existing 3002 first; relevant unit,
integration and desktop/narrow browser checks. Fresh restore-verified backup before
live migrations; local3001 only after checks. Update verification/migration/rollback
docs and commit verified source. No public deploy, purchases, unrelated features or
external test messages. Keep DEV-CHECKPOINT.md under approximately100 lines; targeted
reads and checks, no repeated whole-repository/report scans.
