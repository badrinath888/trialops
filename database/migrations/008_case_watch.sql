CREATE TABLE case_watches (
 workspace_id UUID, case_id TEXT NOT NULL, status TEXT NOT NULL CHECK(status IN ('active','paused','disabled')),
 actor_id UUID NOT NULL REFERENCES users ON DELETE CASCADE, selected_evidence JSONB NOT NULL DEFAULT '[]',
 cursor JSONB NOT NULL DEFAULT '{}', cursor_hash TEXT NOT NULL DEFAULT '', pending_hash TEXT, pending_since TIMESTAMPTZ,
 pause_reason TEXT, version INT NOT NULL DEFAULT 1, updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 PRIMARY KEY(workspace_id,case_id), FOREIGN KEY(workspace_id,case_id) REFERENCES cases ON DELETE CASCADE
);
CREATE TABLE case_watch_updates (
 workspace_id UUID, id UUID, case_id TEXT NOT NULL, trigger_key TEXT NOT NULL, state_hash TEXT NOT NULL,
 changes JSONB NOT NULL, uncertain JSONB NOT NULL, next_action TEXT NOT NULL, refs JSONB NOT NULL,
 model JSONB NOT NULL, superseded BOOLEAN NOT NULL DEFAULT false, created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 PRIMARY KEY(workspace_id,id), UNIQUE(workspace_id,case_id,trigger_key),
 FOREIGN KEY(workspace_id,case_id) REFERENCES cases ON DELETE CASCADE
);
CREATE INDEX case_watch_updates_case ON case_watch_updates(workspace_id,case_id,created_at DESC);
ALTER TABLE jobs DROP CONSTRAINT jobs_kind_check;
ALTER TABLE jobs ADD CONSTRAINT jobs_kind_check CHECK(kind IN ('investigate','index','evaluate','assess','watch'));
