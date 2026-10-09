# TrialOps 2.0 integrated release

This release extends the existing application and database. It preserves the graphite/copper design, workspace roles, durable investigations, exact citations, unsent escalation drafts and separate recommendation decisions.

## Feature locations

| Feature | Location and behavior |
| --- | --- |
| Reviewed checks | Case → Evidence & follow-up → Checks. Exact cited sections/versions become marked suggestions. Edit/save before a reviewer activates. Each assessed item retains notes, evidence, actor and time. Structural changes require reactivation. |
| Missing information | Case → Information requests. Structured items, investigation, owner/deadline, draft/requested/received/cancelled and derived overdue status. Responses retain evidence/actor/time. Copying and status updates send no message. |
| Snapshot comparison | Case → Comparisons & related cases. Compare ordered observations in the same workspace/study/site using stable record IDs; added/missing/changed/unchanged include both times. Missing records do not prove resolution. |
| Evidence-backed resolution | Case → Supporting observations and Case status. Record what you personally verified. Resolution requires approved support, activated assessed checks, evidence from the current open/reopened cycle, reviewer note, verification time and explained exceptions. Historical snapshots alone cannot close a case. |
| Related cases | Case → Comparisons & related cases. Scoped lexical suggestions explain shared terms, differences and outcomes; humans confirm links. Similarity does not establish a common cause or close linked cases. |
| Measured activity | Overview → Measured activity. Queue, worker elapsed, successful run duration, review turnaround and reopening/resolution cycles are separate. Human minutes exist only when explicitly entered under Case → Human effort. ROI remains an assumptions-based scenario. |
| Record flags | Case → Comparisons & related cases. Actual record IDs/times underpin conflicts, missing groups, scope and chronology warnings. Settings → Data policy optionally sets freshness hours; no universal freshness cutoff. |
| Procedure impact | Knowledge → Procedure changes and reassessment. Retained versions produce diffs and notices for open investigations citing older procedures. Reviewers record needed/not-needed rationale. Historical results, approvals and drafts remain frozen. |
| Monitoring preparation | Operational records → Monitoring-visit preparation. Dated study/site view of open issues, incomplete checks, requests, owners/deadlines, configurable visit checks and text export. No compliance/readiness score. |
| In-app reminders | Overview → In-app follow-up reminders; Settings → Data policy. Durable worker scans overdue requests, unfinished checks, reassessment and approaching deadlines; per-user preferences/read state and unique condition keys prevent duplicates. No external delivery. |
| CSV/JSON preview | Operational records → Preview CSV/JSON record import. Generic examples, local file/text input, field mapping, accepted/rejected rows and explicit commit. Immutable snapshot IDs, scope/timestamps and replay handling are enforced. |
| Complete case package | Case → Case package JSON/PDF. Includes cited versions, frozen run records/drafts, history/comparisons, checks, requests/responses, decisions, current verification, events, unresolved items/exceptions and explicit effort. Authentication/workspace scope apply. PDF paginates and escapes untrusted long text. |
| AI evaluation | Knowledge → AI evaluation dashboard, owner/reviewer only. Nine versioned synthetic scenarios exercise the actual configured selection/policy code. Results record citation validity, abstention, draft-rule checks, flags, execution failures, latency, configuration, dataset hash and execution time. Subjective human judgment is separate. |
| Sample walkthrough | Overview in an isolated sample workspace. Six steps, persistent progress, skip/resume, idempotent newer sample observations and links to real case workflows. Permanent workspaces cannot invoke sample mutations. |

## Complete walkthrough

1. Choose **Explore a sample case**. Follow the Overview walkthrough or open **CASE-4**.
2. Run an investigation. Inspect the exact cited sections and dated records; approve the recommendation only after review.
3. Under **Checks**, suggest checks, edit the draft to reflect your reviewed procedure, save and activate.
4. Draft an information request, choose an owner/deadline, record requested status and copy its text if needed. The application does not send it.
5. Under **Supporting observations**, enter a current human verification with its time and what you checked. Record received information and evidence references.
6. Assess each active check. Verified checks require evidence; follow-up/not-applicable states require explanations.
7. In the sample walkthrough, load updated observations. Compare the earlier and later snapshots; confirm related-case links only after reading their differences.
8. Record explicit human minutes if you measured them. Reviewers can resolve separately in **Case status**, citing a current human observation and explaining exceptions. Reopen with a reason if necessary; prior resolution evidence remains in chronology.
9. Export the complete case PDF/JSON. Inspect measured activity on Overview and create a dated monitoring-preparation view in Operational records.
10. Try a procedure edit and its reassessment notice. Run the synthetic evaluation dashboard. Unsupported requests cannot be approved; procedure changes do not rewrite prior decisions.

## Storage and migration

`database/migrations/001_integrated_workflows.sql` adds workspace policies, retained procedure versions, immutable snapshot history, checks, requests, observations, comparisons, related links, reassessment, effort, visits, notification preferences/read state, reminder scans, import previews, evaluations and walkthrough progress. It backfills the current knowledge version. `002_workflow_concurrency.sql` adds idempotent intake submission IDs and renewable job leases.

`apps/api/migrate.py` uses a transaction/advisory lock and records each migration's SHA-256 in `schema_migrations`. Repeated startup does not reapply an existing migration; changed applied SQL is rejected. Existing operational evidence is backfilled without replacing its content. Existing historical resolutions remain valid audit records; new resolutions use the stronger evidence flow. Earlier full procedure versions that were never stored cannot be reconstructed: diffs disclose when they use frozen cited sections only.

API startup applies migrations before serving traffic. The worker waits for API health. Stop application writers during a live upgrade, create/restore-verify a backup, rebuild only `api`, `worker`, `web`, then start them with `--no-deps --wait`. PostgreSQL's service/volume and original secrets/configuration remain in place. Never reset the database.

## Verification and rollback

Use `bash scripts/release-test.sh` to build and test a separate Docker project/volume at http://localhost:3002. It includes unit, real API/worker/MCP, concurrency, interrupted evaluation/retry, browser journey and rendered UI measurement checks. Chromium can be installed with `cd tests/browser && npx playwright install chromium` if missing.

Before live migration, run `bash scripts/verify-backup.sh`. It dumps the existing database, restores into a uniquely named temporary database, checks tables/vector extension and drops only the temporary verification database. Keep its `.dump` and checksum in access-controlled storage. It does not replace live data.

An application rollback can restore the previous API/worker/web image tags while keeping the additive schema. Old code does not know new workflow tables; returning to the new release retains those records. A database rollback loses post-backup writes and requires an operator-controlled maintenance window and explicit use of `scripts/restore.sh`; it is never run automatically. Preserve `.env`, `.secrets`, uploads, backups and the original database volume.

## Configuration and limits

- Existing `.env` values and Ollama model/URL remain unchanged. `AI_MODE=procedure` identifies text matching; `AI_MODE=ollama` uses configured local source selection. Cases always identify actual mode. No external model/service is silently substituted.
- Settings allow optional freshness hours, deadline lead time, reminder scan frequency (15 minutes–7 days), visit template and personal notification kinds. Notifications persist through worker restarts; scans run according to configured frequency. Unchanged conditions do not repeatedly generate new reminders.
- Imports currently accept **synthetic generic records only**, consistent with the application's evidence contract. Preview limits: 100 KB, 200 rows, 10 records per kind/snapshot. Every rejected row has a reason. This is not a vendor connector or a live operational feed.
- Automatic draft rules remain tied to the exact canonical KB-001 15-minute pending-certificate and KB-004 failed-sync procedures. Edited/custom procedures can be cited but do not acquire invented executable thresholds.
- Evaluation inputs are versioned supplied synthetic sources, **not a live vector-retrieval benchmark or clinical validation**. Deterministic assertions and human usefulness judgments remain separate; failures are displayed as recorded outcomes.
- Snapshot list is capped at 500, visits at 100, reassessment notices at 500, notifications at 100 and evaluations at 50. Case queue and saved investigations retain pagination. These are bounded local evaluation views, not an enterprise-scale claim.
- Browser verification uses headless Chromium at simulated widths. It does not establish Safari/Firefox, real-device, screen-reader or comprehensive WCAG certification. Actual executed model/visual/restore results are recorded in RELEASE-VERIFICATION.md.

## This installation: rollback commands

The October 9 upgrade retained runnable local rollback images as
`trialops-release-{api,worker,web}:pre-integrated-20261009`.
Docker had lost the original image content digests, so the running application
files were exported/imported with their commands, environment, working directory
and user preserved. Mounted secrets and the database were excluded. The rollback
API/worker import successfully and the web server passes Node syntax checks. The complete rollback stack has not been activated.
Do not prune these tags until the release is accepted.

For an application-only rollback during maintenance:

```sh
docker compose stop web api worker
docker compose -f compose.yaml -f compose.rollback.yaml up -d --no-deps --no-build --wait api worker web
```

Keep the database schema and original volume. This returns to the earlier UI/API;
new workflow records remain stored but are unavailable in that UI. Restore the
integrated application with `docker compose up -d --no-deps --no-build --wait api worker web`.
Rollback if service health cannot recover, an existing permanent-data fingerprint
changes unexpectedly, or the investigation/review/evidence workflow fails.
Investigate before any database restore; that operation discards later writes and
is deliberately outside automatic application rollback.

Fresh verified archives and SHA-256 files are in the private ignored `backups/`
directory. Current account counts/content fingerprints and rollback image IDs
are in ignored `artifacts/release/resume/`. They are local operator evidence,
not source deliverables. The original database containers and secret files are
retained. Port 3002 remains usable with its permanent account and draft checklist.
