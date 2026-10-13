# Improvement workflows (recurrence, readiness, procedure impact, bulk actions, feedback queue)
Base commit 68b4a94. Additive migration `database/migrations/009_improvement_workflows.sql` (new tables only). Backend: `apps/api/improvement.py`
(router; no model calls, nothing confirmed, resolved, reopened or sent). UI: `apps/web/app/improvement-panels.tsx`. Proxy allowlist: `apps/web/app/api/[...path]/route.ts`.

| Feature | Where in the app | API |
|---|---|---|
| Recurring issues → prevention plans | Case page, “Recurrence & prevention” panel under Case watch | `/recurrence/*`, `/prevention-plans/{id}` |
| Document readiness tracker | Operational records page; summary also in monitoring visit data | `/readiness*` |
| Procedure-change impact review | Knowledge page | `/knowledge/{id}/impact-review` |
| Bulk owner/deadline changes | Cases table (checkbox column + bulk bar, reviewers/owners, open cases) | `/cases/bulk/preview`, `/cases/bulk/apply` |
| Feedback-to-improvement queue | Feedback page (owners: queue + improvements; everyone: own status) | `/feedback/queue`, `/feedback/{id}/triage`, `/feedback/mine`, `/improvements` |

## Rules implemented
- **Recurrence:** candidates come only from identical category + study + site, or reviewer-confirmed case links; text similarity is not used. A reviewer confirms membership and writes the observed pattern (≥20 chars). Members removed later stay in history with a reason. Plans: draft → active → completed (never backwards; completed is read-only); activation needs ≥1 action each with a workspace-member owner, deadline and supporting evidence from a group case; every revision stores a snapshot in `improvement_events`. Measurement: reviewer-selected non-overlapping windows; counts are live matching cases per window. A comparison is shown only when windows have equal length, both have the same exposure unit, and the baseline has ≥5 cases, and is then descriptive rates per exposure unit with the note that it shows no causal improvement; there are no percentage reductions. Case audit events never claim a root cause.
- **Readiness:** requirements are per study (optionally one site); records hold applicability (reason if not applicable), document identity/version, optional expiry (never inferred), observation date, evidence (note or same-site case evidence) and review status. Status is derived: missing / expired / awaiting review / reviewed (+ not applicable). Editing a requirement bumps its version, so records made against an earlier version show “awaiting review” and cannot be reviewed until re-recorded. Reviewed text states it is a dated observation, not a current verification or certification.
- **Procedure impact:** deterministic passage comparison (labelled not AI) of two retained versions; lists active/draft checks and case runs that cited the older version with their past decisions; the reviewer records “reassessment needed / not needed” with a reason (versioned, hash-checked). Checks, runs, cited versions and past decisions are never changed. Archived and superseded states are shown. Versions saved before retention began cannot be compared.
- **Bulk actions:** ≤25 cases; owner and/or deadline only; preview first; per-case transactions that recheck membership, role, state, pending handover and the previewed `updated_at`; results per case (updated / unchanged / stale / failed); `request_id` makes retries safe and resumable; each change is audited as `case_assignment_updated` with the batch id. Resolved cases are refused; nothing is approved, confirmed, resolved or reopened.
- **Feedback queue:** owner-only triage with states received/reviewing/planned/in progress/completed/declined, owner, internal note, safe public note, optional confidential flag, related feedback and tracked improvements. Submitters see only their own feedback in the current workspace with state, safe note and improvement title; confidential items show only received/reviewing. Feedback, triage and improvements are excluded from every export. No publication or external message.
- **Exports:** the case package (JSON/PDF) gains `recurrence` and `procedure_impact` sections (owners/reviewers); the workspace export gains the new tables and `improvement_history` (feedback scopes excluded).

## Verification (actual, port 3002 test stack)
See DEV-CHECKPOINT.md for the latest run list; commands: `docker exec <test-api> python /app/tests/improvement_integration.py` (11 groups), `node tests/browser/improvement-check.cjs` (desktop + 390px journey), plus the existing regression suites.

## Limits
Eligible owners are current workspace members (feedback and improvement owners must be workspace owners). Group scope is category + study (+ site). Readiness evidence supports notes and same-site case evidence only. Impact comparison is passage-level, not semantic. Windows are immutable once recorded. No notifications are sent for these workflows.

## Rollback
Images tagged `pre-improvement-68b4a94` for api, worker and web. Roll back by retagging those as `latest` and `docker compose up -d --no-deps --no-build api worker web`. Migration 009 only adds tables; older code ignores them, so the schema is left in place.
