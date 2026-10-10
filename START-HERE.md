# TrialOps 2.0 · existing installation

The release is developed directly in `~/Downloads/trialops-release`. Continue using http://localhost:3001 and your existing account. Refresh with **Cmd + Shift + R** after an upgrade. No replacement application or repeated ZIP installation is required.

Start an isolated sample workspace with **Explore a sample case**. Overview now has a resumable six-step walkthrough covering a missing certificate, failed synchronization, healthy records, unsupported requests, updated observations and separate human verification/resolution. Skipping preserves your progress. Sample data expires after 24 hours and stays separate from permanent accounts.

Read [RELEASE-2.0.md](RELEASE-2.0.md) for feature locations, a complete workflow, migration/backup instructions and tested limits. [RELEASE-VERIFICATION.md](RELEASE-VERIFICATION.md) records executed checks and deployment evidence.

For future source upgrades in this same folder:

```sh
cd ~/Downloads/trialops-release
bash scripts/release-test.sh
bash scripts/verify-backup.sh
docker compose build api worker web
docker compose up -d --no-deps --wait api worker web
```

The test script uses a separate Docker project and database at port 3002. The backup check restores into a uniquely named temporary database and removes only that verification database. API startup applies checksum-verified additive migrations; the worker waits for API health. Do not delete the database volume, replace `.env`/`.secrets`, or run `docker compose down -v` during an upgrade.

A new installation can still use `bash install.sh` from this directory. Public deployment is separate and requires your own host/domain: [PUBLIC-DEPLOY.md](PUBLIC-DEPLOY.md). No public hosting or external messaging is enabled by this release.

Connected wording/linkage/question workflows: [guide](CONNECTED-ASSESSMENTS.md), [verification](ASSESSMENT-VERIFICATION.md).
