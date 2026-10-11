Build the next integrated TrialOps release:
“My work today + Guided next step + External responses.”

Work in ~/Downloads/trialops-release.
Last reported release: 3276aa8; checkpoint commit: b7f886c.
Live: port 3001. Existing isolated test stack: port 3002.

START
Read applicable AGENTS.md, DEV-CHECKPOINT.md, Git status/diff, and relevant source only. Verify what already exists and extend it rather than duplicating features. Preserve unrelated changes and all existing data.

Save this scope as USER-WORKFLOW-SPEC.md and update the concise checkpoint after milestones. Avoid repeatedly reading whole files or release reports.

1. MY WORK TODAY
Extend Overview with a compact personal queue:
- Cases assigned to me.
- Overdue checks and follow-up deadlines.
- Outstanding requests needing my attention.
- Handovers awaiting my acknowledgment.
- Blocked cases with their responsible person and follow-up date.

Use existing records, reminders, assignments, blockers, and handovers.
Distinguish “I need to act” from “Waiting on someone.”
Explain why each item appears and link directly to its action.
Provide useful empty states and team visibility only where authorized.
Do not create a second notification system or invent deadlines.

2. GUIDED NEXT STEP
Add one compact “Next step” panel to each case.
Derive available actions deterministically from current workflow state.

Examples:
- Run investigation.
- Review findings.
- Review and activate suggested checks.
- Complete outstanding checks.
- Request missing information.
- Review a received response.
- Consider recording resolution when existing requirements are satisfied.

Show the primary action and, when needed, a short explanation of blockers.
Keep other valid actions accessible.
Recompute after changes and handle stale state safely.
Reuse all existing server-side approval and resolution requirements.
Never automatically approve, confirm evidence, or resolve a case.
Do not treat a historical snapshot or completed checklist alone as proof of resolution.

3. EXTERNAL RESPONSE PORTAL
Extend existing information requests with an optional restricted response link.

An authorized member selects a directory contact and explicitly creates a link.
Do not automatically send an email or message.
The contact opens a simple page showing only the specific question and the minimum necessary context.

Security:
- High-entropy opaque tokens; store token hashes.
- Expiring and revocable, scoped to one request and workspace.
- No access to cases, other requests, internal notes, or workspace navigation.
- Treat possession of a link as access, not verified recipient identity.
- GET requests must not consume tokens or modify records.
- Rate limits and bounded submissions.
- Prevent token leakage through logs, analytics, referrers, exports, or third-party assets.
- Recheck expiry, revocation, request status, and workspace policy at submission.
- Handle retries and concurrent submissions without duplicate responses.
- Fail closed when a request is withdrawn or no longer eligible.

Allow a written response. Reuse an existing secure attachment pipeline only if suitable; otherwise keep this release text-only and state that clearly.
Treat all submitted content as untrusted.
Record external attribution honestly, timestamp, and provenance.
Responses remain pending human review; they do not automatically establish truth or complete checks.
Let an authorized reviewer accept the response for consideration or request clarification, with an audit trail.
Notify through existing in-app reminders.
Show clear expired, revoked, already-submitted, and unavailable states.

UX
Retain graphite/copper, readable typography, compact cards, and consistent buttons.
No extra top-level navigation.
Use short labels and expandable details.
Support keyboard use, narrow layouts, loading, errors, and permission states.
Preserve unsaved drafts where practical.
No new LLM calls.

VERIFY
Test workspace and role isolation, personal queue accuracy, next-step transitions,
stale state, token expiry/revocation, withdrawn requests, duplicate/concurrent
submissions, malicious content, and truthful external attribution.

Run a populated desktop/narrow journey:
owner requests evidence → copies restricted link → external visitor responds →
owner reviews response → completes necessary checks → resolves separately.

Check existing-feature regressions and readable JSON/PDF exports.
Exports must exclude access tokens and unnecessary contact details.

DELIVER
Implement and test in the existing port 3002 stack first, preserving its records.
Before live migrations, create and restore-verify a fresh backup.
Deploy locally to port 3001 only after checks pass.
Preserve accounts, databases, secrets, uploads, backups, and prior features.
Update feature locations, actual verification results, security notes, and rollback instructions.
Commit verified source and provide a concise walkthrough.

No public deployment, external sending, purchases, unrelated features, or unnecessary rebuilds.
Continue until the integrated release is verified; checkpoint any interruption.