# Connected assessments — extension of 58cea0a

## Locations and workflow

All fourteen integrated features remain available. On a saved investigation, **Check wording** is beside review notes; on a case it is beside resolution rationale. In **Evidence & follow-up**, expand **Review record linkage** for the linkage action and **Suggest next question** tab. Explicitly select relevant records/procedures before requesting an assessment. Source details include exact fields, frozen versions and observation dates. Corrections are editable suggestions; they never replace the review text.

Wording has four labels: supported by selected evidence, contradicted, insufficient evidence, not assessable. Evidence consistency is not proof of real-world truth. Deterministic cautions flag causal wording and current-status assumptions separately from model labels. A reviewer may record a disagreement and reason. Identifier matches, scope, dates, conflicts and competing candidates are deterministic, not AI assessments. Same site or contextual similarity alone cannot authorize confirmation. A reviewer confirms an eligible candidate with rationale; this does not establish root cause.

Questions address supplied unresolved gaps, cited procedures, completed checks and existing requests. At most three survive deterministic duplicate/intent checks. Convert a chosen question into the existing editable, **unsent** request draft. Record usefulness with a reason. Evidence changes retain old assessments and mark them stale; reassess selected updated evidence. Approval, linkage confirmation, current-evidence verification and case resolution remain separate human actions.

In a new sample workspace, Overview → **Missing certificate · evidence-linkage sample journey** starts an idempotent isolated example. Investigate its case, assess the false causal wording against the certificate and unrelated job, review missing linkage and suggest a focused question. Load the correct receipt/updated record, reassess, confirm exact linkage and complete the existing current-evidence/check workflow before resolving separately. No messages are sent and no case is automatically resolved.

Case package PDF/JSON includes frozen assessment inputs/results/configuration and attributed decisions; analyst exports omit reviewer-only assessments. Historical evidence and incomplete verification warnings remain in the package.

## Architecture and threat model

Migration 003 adds workspace-scoped frozen assessments and append-only human decisions, using the existing durable jobs, audit, requests and worker leases. Authorization is checked at enqueue, worker dispatch, after inference before saving, and before returning results. A lost lease cannot write a result. Membership revocation blocks inference/results. Selected source IDs must exist in the authorized case catalog; study/site and record identifiers/timestamps are checked before dispatch. Results never invoke arbitrary shell, URL, write or external message tools.

Semantic inference uses only local Ollama. Retrieved procedures, records and user wording are untrusted data. A strict JSON schema restricts claims/gaps and server-owned passage references. The server resolves passage IDs to the exact authorized source/field/quotation, validates each substring and adds provenance. Forged references, malformed output, invented identifiers/thresholds and confidence percentages fail closed. This establishes reference validity, not semantic relevance or factual truth. Model labels are not silently replaced with deterministic labels.

A canonical context hash includes case details, saved run/review state, selected-source catalog, procedure versions, policy, checks and requests. Configuration changes also stale results. Cache reuse requires matching input/context/configuration, the same actor and current authorization. Request conversion is transactionally idempotent and preserves an unsent existing request. Assessments never modify frozen evidence or resolve cases.

## Configuration and limits

Keep the existing secrets and database volumes. `OLLAMA_URL` defaults to `http://host.docker.internal:11434`; allowed local hosts are localhost, 127.0.0.1, host.docker.internal and ollama, without embedded credentials. `OLLAMA_MODEL` defaults to `qwen2.5:7b`. No cloud inference is introduced. Assessments work independently of the legacy investigation `AI_MODE`; linkage is deterministic even when Ollama is unavailable.

Semantic configuration records temperature 0, context 8192, output 1800 tokens, 60-second timeout, 20 KB input/response and two total attempts (explicit manual retry). Selected frozen input is limited to 16 KB, 12 sources and 12 claims/2,000 wording characters. Passage chunks are at most 1,200 characters. Shared assessment/evaluation workload is at most two active jobs per workspace; assessment requests are limited to 20/hour/workspace. The case catalog is bounded to 20 snapshots/runs and 30 observations. Large cases must select smaller relevant evidence; explicit errors are preferable to uncontrolled inference. No inference runs on typing, page loading or opening history.

Unavailable Ollama, validation failures, timeout, stale inputs and exhausted retry states are explicit. Worker leases recover interrupted jobs using the existing job system. Duplicate questions use exact intent keys and token overlap; paraphrases can still escape detection. Model interpretation remains fallible. Evaluation fixtures are synthetic, specification-derived and independently labeled; citation validity does not measure relevance. No real human question-usefulness score is inferred from scripted test judgments.

## Deployment and rollback

Test on the separate `trialops-release-test` project first. Before live migration, preserve current application image tags, stop only live web/api/worker writers, record existing-data fingerprints, and run `bash scripts/verify-backup.sh`. This restores into a separate temporary database and retains a private archive/checksum; it never replaces live data. Migration 003 is additive. Deploy only api/worker/web with `--no-deps --wait`; leave PostgreSQL, volumes, credentials, uploads and both databases intact.

For an application rollback, stop live application writers and run:

```sh
docker compose -f compose.yaml -f compose.assessments-rollback.yaml up -d --no-deps --no-build --wait api worker web
```

The prior 58cea0a application ignores additive assessment tables. New records remain for a subsequent forward deployment. Roll back for failed health, authorization regression or incorrect workflow behavior. Do not downgrade/drop tables or automatically restore a database. A database restore loses later writes and requires a separately authorized maintenance procedure; preserve the new backup first. The older `compose.rollback.yaml` belongs to the previous fourteen-feature release and is not this extension's rollback.

Actual verification, backup/deployment identifiers and coverage limits are recorded in ASSESSMENT-VERIFICATION.md after execution. Backups, uploads, secrets, screenshots and generated exports are ignored and excluded from source commits.
