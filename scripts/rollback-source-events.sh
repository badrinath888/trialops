#!/usr/bin/env bash
# Step 1 of rolling back migration 013 (source events): run BEFORE starting old api/worker images.
# Pauses enabled sources (ids saved for re-enabling), stops the worker, then fails any queued/running source_event
# jobs so an old worker never claims a kind it does not know. Events stay 'received' (nothing lost); after a
# roll-forward, enable the sources again and scan_sources re-queues them. Schema is left as is (additive).
# Test stack: COMPOSE="docker compose -p trialops-release-test -f compose.yaml -f compose.release-test.yaml" bash scripts/rollback-source-events.sh
set -euo pipefail
cd "$(dirname "$0")/.."
COMPOSE=${COMPOSE:-docker compose}
psql() { $COMPOSE exec -T db psql -v ON_ERROR_STOP=1 -U trialops -d trialops -At "$@"; }
mkdir -p backups
saved=backups/rollback-paused-sources-$(date +%Y%m%d-%H%M%S).txt
psql -c "UPDATE source_connections SET status='paused',updated_at=now() WHERE status='enabled' RETURNING workspace_id||' '||id" | grep -v '^UPDATE' > "$saved" || true
echo "paused $(wc -l < "$saved" | tr -d ' ') source(s); ids in $saved"
$COMPOSE stop -t 120 worker
psql -c "UPDATE jobs SET status='failed',finished_at=now(),lease_token=NULL,error='Rolled back before processing; the event is kept and is re-queued after roll-forward.' WHERE kind='source_event' AND status IN ('queued','running')" | cat
left=$(psql -c "SELECT count(*) FROM jobs WHERE kind='source_event' AND status IN ('queued','running')")
[ "$left" = 0 ] || { echo "FAIL: $left source_event job(s) still queued/running" >&2; exit 1; }
echo "OK: worker stopped, sources paused, no queued/running source_event jobs. Next: up -d --no-deps --no-build --wait api worker web with the rollback images."
