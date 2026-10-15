#!/usr/bin/env bash
# Read-only content fingerprint (row count + md5 of all row text) per pre-existing table of the live DB.
# Run before and after deploy; `diff` the two outputs. Volatile tables are excluded; new journey tables are not listed; case_watch_updates ignores the migration-013 columns source_event_id/detail.
set -euo pipefail
cd "$(dirname "$0")/.."
docker compose exec -T db psql -v ON_ERROR_STOP=1 -U trialops -d trialops -Atc "
SELECT string_agg(format('SELECT %L AS t, count(*) AS n, coalesce(md5(string_agg(%s, E''\n'' ORDER BY %s)),''-'') AS h FROM %I x', table_name, v, v, table_name), ' UNION ALL ' ORDER BY table_name)
FROM information_schema.tables, LATERAL (SELECT CASE WHEN table_name='case_watch_updates' THEN '(to_jsonb(x)-''source_event_id''-''detail'')::text' ELSE 'x::text' END AS v) q WHERE table_schema='public' AND table_type='BASE TABLE'
AND table_name NOT IN ('sessions','rate_limits','schema_migrations','jobs','reminder_scans') AND table_name NOT LIKE 'journey\_%' AND table_name NOT LIKE 'source\_%' AND table_name<>'automation_settings'" \
| docker compose exec -T db sh -c 'psql -v ON_ERROR_STOP=1 -U trialops -d trialops -At -F" " -f - ' | sort
