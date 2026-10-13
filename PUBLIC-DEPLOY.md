# Publish the evaluation application

First complete the Mac installation and acceptance checks. Publish the application as an **operational evaluation using synthetic data**. The source is ready for hosting; it has not been deployed to a public server by this package.

## Server and DNS

Use a Linux server that you administer with Docker Engine and Docker Compose v2 supporting `!reset` overrides. The public configuration needs an accessible hostname, working DNS, and inbound TCP 80/443 (UDP 443 is optional). Database and API ports are not published. Keep SSH limited to your administration access.

Procedure mode avoids exposing your Mac or incurring a remote inference dependency. Decide server capacity by measuring the included workload; the package does not promise a visitor count or performance SLA.

Copy the extracted `trialops-release` folder to the server. Point your domain's DNS records to it. Then, **on the server**, run:

```bash
cd trialops-release
bash deploy.sh trialops.YOUR-DOMAIN.com
```

Replace the hostname. `deploy.sh` only initializes a fresh configuration. It writes `DOMAIN` and `COMPOSE_FILE=compose.yaml:compose.production.yaml` to `.env`; Docker Compose and the maintenance scripts then use the HTTPS overrides automatically. Caddy obtains a TLS certificate after DNS and connectivity are correct. If it fails, inspect `docker compose logs --tail=100 caddy`; do not disable cookie security to bypass the problem.

For an existing configuration, back up first, add those two settings to `.env`, set `AI_MODE=procedure`, and run `docker compose up -d --build --wait`. On a server the installer will preserve existing `.env` and secrets. Use the actual HTTPS hostname, not localhost, for the browser.

## Verify before sharing

```bash
docker compose ps
bash scripts/test.sh
bash scripts/backup.sh
```

The server-side test suite uses private HTTP API access with the internal key. Secure-cookie production sessions require HTTPS in a real browser. For the internal integration harness only, the test client explicitly handles those secure cookies over the private API connection; this does not change the browser cookie configuration.

Complete these checks in the deployed browser:

- Open the public homepage on desktop and mobile, without an account.
- Start a sample workspace in two separate private browser sessions. Each must have independent cases and decisions.
- Investigate CASE-4, review its source and dated records, approve with notes, and resolve it separately.
- Investigate CASE-7: it must abstain and disallow approval. CASE-6 must not create a failed-job or overdue-certificate escalation.
- Create an account, sign out, sign back in, and verify its saved case/history remain.
- Invite an analyst account. That account must not be able to approve or edit knowledge.
- Upload a text procedure, verify extraction, save/edit/archive/restore, and reopen an earlier saved investigation to confirm frozen evidence.
- Submit feedback; confirm the operator can export it.
- Check browser console/network errors and server logs. Confirm only HTTPS is publicly serving the UI and cookies have Secure, HttpOnly, and SameSite=Lax attributes.
- Verify a backup restore on a separate test deployment. An archive-listing check alone does not prove restore success.

## Collect feedback

Feedback is stored in PostgreSQL; this release does not email it. Export it using an administrator shell on the server:

```bash
mkdir -p exports
docker compose exec -T api python admin_cli.py feedback > exports/feedback.json
```

Keep exports access controlled. Set a retention process for exports and backups separately from the application's 30-day feedback retention. Do not request sensitive documents in feedback.

## Operate and recover

```bash
docker compose exec -T api python admin_cli.py workspaces
docker compose exec api python admin_cli.py reset-password --email verified-requester@example.com
docker compose exec api python admin_cli.py delete-workspace --workspace WORKSPACE-UUID
```

Reset and deletion require an interactive operator and independently verified requester. Deletion asks for the exact workspace UUID. A password reset revokes existing sessions. Deleting a workspace does not erase older backups; apply your retention policy. After changing application code, run the tests, back up, and rebuild. Pin reviewed container image digests for a reproducible hosted rollout; the supplied major-version image tags receive upstream changes.

For public evaluation, review `.env` settings `ENABLE_DEMO`, `ENABLE_SIGNUP`, `DEMO_HOURLY_LIMIT`, and `SIGNUP_HOURLY_LIMIT`. Turn off signup or sample creation if you want a restricted trial. Application rate limits are a basic control, not a complete anti-abuse system. Add platform monitoring and independent security review before broad or sensitive use.

## Positioning when sharing

Describe the actual product: an evidence-led clinical operations support application with versioned procedures, historical synthetic snapshots, human review, and tracked resolution. Say when the hosted instance uses procedure matching rather than an LLM. Do not describe scenario ROI as measured savings, or claim patient-data readiness or regulatory certification. Invite feedback through the in-product Feedback page.

## Scheduled offsite backups (not yet performed on a real remote)
`scripts/backup-offsite.sh` dumps the database, restores it into a temporary database (`RESTORE_VERIFY=true`), copies the dump to an
rclone remote, checks the remote size, then deletes local and remote dumps older than `RETENTION_DAYS` (default 14, minimum 2).
Any failed step writes `FAILED ... at step: ...` to `backups/backup-offsite.status` and stderr, and pings `HEALTHCHECK_URL/fail`
if set; success pings `HEALTHCHECK_URL`. Alert on a missed success ping, since a crashed cron job reports nothing.
1. Install rclone on the server; create a private bucket and an application key limited to that bucket (the key must allow delete for retention).
2. `cp .backup.env.example .backup.env; chmod 600 .backup.env`; replace the placeholders.
3. Run once by hand: `bash scripts/backup-offsite.sh`, then list the remote and restore that file on a separate host with `scripts/restore.sh` before relying on it.
4. Schedule: `17 3 * * * cd /path/to/trialops-release && bash scripts/backup-offsite.sh >> backups/cron.log 2>&1`.
Dumps contain all workspace data and are not encrypted by this script; use a private bucket and enable provider-side encryption.

## Client addresses and rate limits
Per-visitor limits use the address the web tier sends to the API. The web tier trusts `X-Forwarded-For` only when `TRUST_PROXY=true`,
which `compose.production.yaml` sets because Caddy is then the only way to reach web (no published port) and Caddy overwrites the header
with the real peer address; web uses the last entry. Without it (local runs) the header is ignored and all visitors share one bucket.
Do not set `TRUST_PROXY=true` or publish the web port if anything other than Caddy (or another proxy you control that overwrites the header)
can reach web. If you put Cloudflare or a load balancer in front of Caddy, all visitors will appear as that proxy until Caddy is configured with `trusted_proxies` for it.
`tests/proxy_ip_check.sh` was run once on the test stack (Caddy with the production directives, plain HTTP): spoofed-header rotation did not evade the
login limit, a second real source had a separate limit, and untrusted mode ignored the header. Not yet tested behind a real HTTPS domain.
`APP_PUBLIC_URL` (used in emailed links) is now set from `DOMAIN` for API and worker in the production override.
