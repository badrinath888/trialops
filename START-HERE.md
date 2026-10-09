# TrialOps 1.4.1 · Graphite & Copper

## Update your existing Mac installation

Extract this ZIP separately. Keep your existing `~/Downloads/trialops-release` folder in place; it contains deployment credentials for your existing database.

From Terminal, run:

```bash
cd ~/Downloads/trialops-1.4.1
bash update-existing.sh ~/Downloads/trialops-release
```

The updater verifies every package file, stops application writers, creates a database backup, saves the replaced source, installs the update, rebuilds services, waits for health checks, runs installation tests, and then removes obsolete source and known disposable build files. Your database volume, accounts, `.env`, `.secrets`, Git history, uploads, and backups are preserved. No global Docker prune is run. If a step fails, the script stops and prints the failure; do not delete the old folder or backups.

Open your existing application URL, normally http://localhost:3001. Press **Cmd + Shift + R** to refresh its styles. Sign in with your existing account.

## Clean installation

Only if you do not have an existing release installation:

```bash
cd ~/Downloads/trialops-1.4.1
bash install.sh
```

The stable Docker project name is `trialops-release`, regardless of the download directory name. A prior database requires the original credentials and the update flow above.

## What changed

- Solid preference choices replace the faint native dropdown menus.

- Compact Overview with one attention queue and recent cases.
- Cases table, requested previews, personal saved views, assigned/review/overdue filters.
- Shorter findings with full procedures and evidence available on request.
- Knowledge table with inspection before editing and reviewed upload extraction.
- Personal spacing and sign-in start-page preferences, separate from team settings.

See WORKFLOW-UPDATE.md for details. The Graphite & Copper colors and readable text are preserved.

## Cleanup scope

The updater cleans only the existing release installation: obsolete stylesheet and compact-update note, known web build caches/dependencies, and Python bytecode caches. It does not delete unrelated projects such as `~/Desktop/trialops-ai`, previous downloaded archives outside the installation, database volumes, or backups. Keep the rollback source and database backup until you have checked the updated app.

## Public deployment

This update deploys to your existing local Docker installation. Public HTTPS hosting still needs a server and domain you control. Follow `PUBLIC-DEPLOY.md` for that separate deployment; this package does not create a public URL automatically.
