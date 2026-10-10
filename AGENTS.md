# TrialOps project instructions

## Working rules for release resumptions

- Read applicable AGENTS.md instructions, DEV-CHECKPOINT.md, and Git status/diff first.
- Verify checkpoint claims against changed files and actual code; the checkpoint is a guide.
- Preserve existing implementation, unrelated edits, both databases/accounts/records,
  uploads, secrets, backups, frozen evidence, permissions and audit history.
- Read affected functions and necessary dependencies using targeted rg searches.
  Avoid whole reports, large source files, generated files, dependencies and old
  transcripts unless they are needed to resolve a specific uncertainty.
- Once relevant code is understood, implement the authorized scope. Do not restart
  completed work, reduce scope, add unrelated features or repeat architecture summaries.
- Keep tool output and progress updates concise. Run targeted checks while editing,
  then required integrated checks before deployment. Repeat checks/builds only for
  changes, failures or unresolved concerns. Report actual results and coverage limits.
- Test on the isolated port 3002 stack first. Before live migrations, create and
  restore-verify a fresh backup, record preservation invariants and retain rollback
  images. Deploy only affected services locally to port 3001; never reset databases.
- Preserve bounded explicit-request local Ollama inference; use deterministic logic
  for authorization, scope, identifiers, dates, staleness, duplicates and citations.
  No paid inference, automatic sending/resolution or public deployment.
- Maintain one current DEV-CHECKPOINT.md under approximately 100 lines, with commit,
  relevant uncommitted changes, file responsibilities, completed implementation and
  actual checks, remaining work/exact next action, and test/live commands.
- Update the checkpoint after milestones and before interruption. Never put secrets
  or private record contents in instructions/checkpoints. Retain historical reports
  as verification references, not parallel working checkpoints.
- Commit verified source only; exclude secrets, backups, uploads and generated artifacts.
