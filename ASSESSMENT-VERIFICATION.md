# Connected assessment verification — October 9, 2026

Extension of commit 58cea0a. The fourteen-feature ledger remains in RELEASE-VERIFICATION.md; this file records the connected-capability release. Test workspaces are newly created isolated samples; permanent accounts and saved records are not reset.

## Completion ledger

| Capability | Implementation / location | Verification |
|---|---|---|
| Check wording | Saved investigation review notes; Case resolution rationale; evidence workflow tab | Four labels, exact selected-source provenance, causal/history cautions, editable suggestions, attributed disagreement, frozen history |
| Review record linkage | Case → Evidence & follow-up | Deterministic scope/IDs/dates, exact/contextual separation, missing/conflicting/competing candidates, human rationale and audit, stale results |
| Suggest next question | Evidence workflow tab | Bounded local semantic generation from cited procedures/checks/requests/gaps; deterministic duplicate checks, unsent existing request conversion, recorded usefulness reason |
| Shared delivery | Assessment jobs/API, migration 003, exports/evaluation | Current authorization rechecks, workload/retry bounds, strict output/passages, lost-lease protection, PDF/JSON history |

## Executed checks

- 50 unit tests passed, including eight focused assessment tests. Server-owned passage mapping rejects unknown reference IDs and attempts to rewrite quotations; existing exact-source/field/substring validation remains in place.
- 15 existing integration groups, 10 fourteen-feature release integration groups, and five boundary groups passed. The existing nine-scenario procedure worker evaluation passed within these checks.
- Seven final connected workflow/security groups passed: cross-workspace and forged-source denial; actual local causal assessment and authorized cache/disagreement; question/draft idempotency; updated exact receipt, stale frozen history and attributed confirmation; revoked permission before dispatch/return and after inference; lost lease/interruption and explicit timeout failure.
- Existing baseline browser checks passed: saved investigations, review, separate resolution/reopening, uploads/knowledge, scope/intake, feedback/export, responsive widths and cross-origin write rejection.
- Populated assessment browser checks, complete resolved demo, final original workflow browser review and export inspection are recorded below when complete.
- Production Docker builds compile API/worker and Next/TypeScript successfully. Only affected application images are deployed.

## Independent model-quality evaluation

`assessments-v1` contains 13 manually specification-labeled synthetic scenarios. The evaluated model did not author ground truth. Local `qwen2.5:7b`, semantic-5, temperature 0, 8192 context, 1800 output tokens, 60-second timeout. Dataset SHA-256: `d15120adf9a13ba38fec2ca5f6fe0b3f99f96c384919f8893e769dd1da1110e9`.

Final results: **7/7 claim labels correct (100%)**; **8/8 semantic results with valid selected-evidence citations (100%)**; deterministic linkage **TP 2 / FP 0 / FN 0**, precision/recall **100%**. Both question scenarios met their expected bounded/nonduplicate behavior. **0 execution failures**. Mean latency across all 13 cases: **5.325 s**. Across eight actual semantic calls: mean **8.653 s**, median **7.174 s**, maximum **19.243 s**. Deterministic no-gap results are excluded from semantic citation metrics.

Cases include facts, contradiction, unsupported causation, stale/current inference, subjective claims, user/source prompt injection, missing IDs, wrong same-site documents, exact receipt, competing records, missing information and answered duplicate questions. Forged references/IDs, malformed output, timeout, revoked access and worker interruption are separate deterministic security tests. No synthetic security pass is represented as model accuracy.

The first semantic-4 evaluation measured 6/7 correct labels and one empty-gap JSON failure. Historical-status guidance and deterministic no-gap handling fixed the verified defects; semantic-5 was evaluated afresh. Earlier failures remain in ignored artifacts. **Zero real human question-usefulness judgments** were supplied; scripted reviewer fixtures verify storage and attribution but are not real usefulness scores.

## Coverage limits

This is a small synthetic benchmark, not a clinical or real-world truth validation. Passage validity guarantees reference provenance, not relevance. Paraphrase duplicate detection and semantic judgments remain fallible. No paid/cloud inference or external messaging was used. Full rollback activation and database rollback are not performed over preserved live data. Bounded catalogs/input and configuration are documented in CONNECTED-ASSESSMENTS.md. Generated reports, screenshots, backups and exports remain private ignored artifacts.

## Final browser/export and deployment results

The final port 3002 assessment browser journey passed populated desktop (1440px) and narrow (390px) checks, saved history, keyboard focus, explicit selections, unchanged review wording, disagreement, draft conversion, stale history, exact confirmation and separate human-current-evidence resolution. No uncaught JavaScript errors or horizontal page overflow were recorded. The original release journey passed **16 populated states / 3,113 measured text instances** with no recorded text-size, contrast, control-height or overflow failures. Populated screenshots were visually inspected, including existing checks/requests/observations/comparisons/effort, visit preparation, procedure evaluation and overview. Full assessment identifiers remain available under expandable provenance, reducing narrow-screen clutter.

The completed sample's **42-page case evidence PDF** was rendered in full and every page visually inspected; no clipped text, overlap or broken page layout was found. JSON assertions verified frozen assessments, attributed decisions, stale flags, unsent request history and separate resolution. The earlier 35-page open-case package was also rendered and inspected. Exports are complete and intentionally verbose; large evidence histories produce long PDFs.

A fresh test backup restored successfully into a separate temporary verification database:
`backups/trialops-test-assessments-verified-20261009-224137-95235.dump`.
Before live migration, only live web/api/worker writers were stopped. A fresh live backup restored successfully into another temporary verification database:
`backups/trialops-verified-20261009-224558-97384.dump`.
Both private archives have retained SHA-256 files. The live restore contained 12 workspaces, 12 users, 99 cases, 12 investigations and 62 knowledge records (including temporary demo data); these are backup-time totals, not permanent-account counts.

Live migration ledger now contains 001, 002 and **003_connected_assessments.sql**. Tested API/worker/web images were tagged into the existing live installation and started with `--no-deps --no-build --wait`. PostgreSQL service/volume was not replaced. Prior live application images are retained as `pre-assessments-58cea0a`; `compose.assessments-rollback.yaml` validates. Original `compose.rollback.yaml` remains available for the prior release.

All four live services are healthy and `/api/health` returns ok. The full connected browser journey also passed on **port 3001** using a fresh expiring sample workspace, through explicit current-evidence resolution and PDF/JSON export. Original permanent-data counts/content fingerprints matched at predeployment, stopped-writer, migrated, deployed and final checkpoints for **both databases**, including users/memberships, cases, frozen runs, knowledge/operations, checks, requests and the other fourteen-feature tables. Thus the user's saved port 3002 account/investigation/draft checklist remain preserved. Three existing private configuration files matched their recorded hashes; no stored upload files were removed or modified. No database reset, secret replacement, public deployment or service purchase occurred. No service error markers were observed in retained postdeployment logs during these checks; this is a smoke/workflow observation, not a long-running load/soak test.

Raw quality JSON, logs, data fingerprints, screenshots and exports are under ignored `artifacts/assessments/`; archives are under ignored `backups/`. Source commit excludes all of them. No implementation item remains blocked; real user usefulness judgments and broader model/load/assistive-technology evaluation remain coverage limits.

Final review also closed the evaluation-retry path's shared workload-cap bypass and aligned assessment retry locking with enqueue locking. Five concurrency/retry boundary groups passed again; an additional real-API, inference-free test confirmed a retry returns 429 when two assessment/evaluation jobs are active, without queuing another job. Eight focused unit tests passed again. Only API/worker images were updated for this fix; the semantic-5 prompt, quality configuration/dataset, web UI and migration were unchanged, so completed model/browser/PDF verification remains applicable.
The final retry boundary also passed on live port 3001. Its counter explicitly excludes unrelated embedding/index jobs; the live installation's existing Ollama indexing queue remains independent. Final original-data fingerprints matched again in both databases after this check.
