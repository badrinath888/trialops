-- Additive: mock source connections, source-scoped event ingestion, quarantine, automation settings. Existing rows are untouched.
CREATE TABLE source_connections (
 workspace_id UUID NOT NULL REFERENCES workspaces ON DELETE CASCADE, id UUID NOT NULL, name TEXT NOT NULL,
 adapter TEXT NOT NULL CHECK(adapter IN ('mock_portal','mock_hub')), status TEXT NOT NULL CHECK(status IN ('enabled','paused','revoked')),
 token_hash TEXT NOT NULL UNIQUE, last_success_at TIMESTAMPTZ, last_error TEXT, last_error_at TIMESTAMPTZ,
 actor_id UUID REFERENCES users ON DELETE SET NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT now(), updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 PRIMARY KEY(workspace_id,id)
);
CREATE TABLE source_events (
 workspace_id UUID NOT NULL, id UUID NOT NULL, source_id UUID NOT NULL, external_id TEXT NOT NULL, source_rev INT NOT NULL,
 observed_at TIMESTAMPTZ NOT NULL, received_at TIMESTAMPTZ NOT NULL DEFAULT now(), schema_version TEXT NOT NULL, content_hash TEXT NOT NULL, payload JSONB NOT NULL,
 status TEXT NOT NULL DEFAULT 'received' CHECK(status IN ('received','processed','unmatched','ambiguous','failed','ignored')),
 reason TEXT, case_id TEXT, attempts INT NOT NULL DEFAULT 0, next_attempt_at TIMESTAMPTZ, duplicates INT NOT NULL DEFAULT 0, result JSONB, processed_at TIMESTAMPTZ,
 PRIMARY KEY(workspace_id,id), UNIQUE(workspace_id,source_id,external_id), FOREIGN KEY(workspace_id,source_id) REFERENCES source_connections ON DELETE CASCADE
);
CREATE INDEX source_events_pending ON source_events(status,next_attempt_at);
CREATE TABLE source_event_conflicts (
 workspace_id UUID NOT NULL, id UUID NOT NULL, event_id UUID NOT NULL, content_hash TEXT NOT NULL, received_at TIMESTAMPTZ NOT NULL DEFAULT now(), payload JSONB NOT NULL,
 PRIMARY KEY(workspace_id,id), FOREIGN KEY(workspace_id,event_id) REFERENCES source_events ON DELETE CASCADE
);
CREATE TABLE automation_settings (
 workspace_id UUID PRIMARY KEY REFERENCES workspaces ON DELETE CASCADE, draft_preparation BOOLEAN NOT NULL DEFAULT false,
 actor_id UUID REFERENCES users ON DELETE SET NULL, updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
ALTER TABLE jobs DROP CONSTRAINT jobs_kind_check;
ALTER TABLE jobs ADD CONSTRAINT jobs_kind_check CHECK(kind IN ('investigate','index','evaluate','assess','watch','source_event'));
ALTER TABLE case_watch_updates ADD COLUMN source_event_id UUID, ADD COLUMN detail JSONB;
