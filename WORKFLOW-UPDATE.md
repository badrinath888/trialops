# TrialOps 1.4.1 · Preference readability

The Content spacing and Default page after sign-in dropdowns are replaced with opaque radio choices, dark text, a clear selected state, and keyboard navigation. Existing saved preferences remain compatible.

# TrialOps 1.4 · Desktop workflows

The Graphite & Copper theme remains. This update changes how information is arranged and accessed.

- **Overview:** inline counts, one attention queue with selectable categories, and recently updated cases. Sample walkthroughs expand on request.
- **Cases:** aligned columns, server-filtered assigned/pending-review/overdue/unassigned views, full-result pagination, personal saved filters, and a requested case preview. Escape closes previews and restores keyboard focus.
- **Investigation:** brief recorded observations, explicit uncertainty, and complete documented checks. Evidence, historical records, and activity remain in separate tabs. Source wording and escalation thresholds are preserved.
- **Knowledge:** procedure/version/category/status table; inspect a procedure before editing. Upload opens extracted text for review. Unsaved edits require confirmation before switching procedures.
- **Settings:** personal Compact/Comfortable spacing and the default page after sign-in. Team management stays separate.

Saved filters are personal to the account and workspace in the same browser. Display preferences are personal to the account in the same browser. They do not sync across devices. Changing spacing does not shrink text.

The update preserves existing sessions, accounts, database, credentials, uploads, saved investigations, and backups. No schema migration is required. Approval still reviews checks; resolution is a separate assessment. Drafts remain unsent.

Use `bash update-existing.sh ~/Downloads/trialops-release` from the separately extracted `trialops-1.4.1` folder. Refresh with Cmd+Shift+R when it finishes.
