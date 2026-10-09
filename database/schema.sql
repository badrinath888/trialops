CREATE EXTENSION IF NOT EXISTS vector;
CREATE TABLE IF NOT EXISTS workspaces (
 id UUID PRIMARY KEY, name TEXT NOT NULL, demo BOOLEAN NOT NULL DEFAULT false,
 created_at TIMESTAMPTZ NOT NULL DEFAULT now(), expires_at TIMESTAMPTZ
);
CREATE TABLE IF NOT EXISTS users (
 id UUID PRIMARY KEY, email TEXT UNIQUE NOT NULL, name TEXT NOT NULL,
 password_hash TEXT, guest BOOLEAN NOT NULL DEFAULT false, created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS memberships (
 workspace_id UUID REFERENCES workspaces ON DELETE CASCADE, user_id UUID REFERENCES users ON DELETE CASCADE,
 role TEXT NOT NULL CHECK(role IN ('owner','reviewer','analyst')), PRIMARY KEY(workspace_id,user_id)
);
CREATE TABLE IF NOT EXISTS sessions (
 token_hash TEXT PRIMARY KEY, user_id UUID REFERENCES users ON DELETE CASCADE,
 workspace_id UUID REFERENCES workspaces ON DELETE CASCADE, expires_at TIMESTAMPTZ NOT NULL
);
CREATE TABLE IF NOT EXISTS invitations (
 token_hash TEXT PRIMARY KEY, workspace_id UUID REFERENCES workspaces ON DELETE CASCADE,
 role TEXT NOT NULL CHECK(role IN ('reviewer','analyst')), expires_at TIMESTAMPTZ NOT NULL, used_at TIMESTAMPTZ
);
CREATE TABLE IF NOT EXISTS studies (
 workspace_id UUID REFERENCES workspaces ON DELETE CASCADE, id TEXT, name TEXT NOT NULL,
 PRIMARY KEY(workspace_id,id)
);
CREATE TABLE IF NOT EXISTS sites (
 workspace_id UUID, id TEXT, study_id TEXT NOT NULL, name TEXT NOT NULL,
 PRIMARY KEY(workspace_id,id), UNIQUE(workspace_id,id,study_id),
 FOREIGN KEY(workspace_id,study_id) REFERENCES studies ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS cases (
 workspace_id UUID, id TEXT, study_id TEXT NOT NULL, site_id TEXT NOT NULL,
 title TEXT NOT NULL, description TEXT NOT NULL, category TEXT NOT NULL,
 priority TEXT CHECK(priority IN ('low','medium','high')) NOT NULL, status TEXT NOT NULL DEFAULT 'open' CHECK(status IN ('open','resolved')),
 owner_id UUID REFERENCES users ON DELETE SET NULL, due_at TIMESTAMPTZ,
 resolution TEXT, resolved_by UUID REFERENCES users ON DELETE SET NULL, resolved_at TIMESTAMPTZ,
 created_at TIMESTAMPTZ NOT NULL DEFAULT now(), updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 PRIMARY KEY(workspace_id,id), FOREIGN KEY(workspace_id,site_id,study_id) REFERENCES sites(workspace_id,id,study_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS cases_queue ON cases(workspace_id,status,updated_at DESC);
CREATE TABLE IF NOT EXISTS knowledge (
 workspace_id UUID REFERENCES workspaces ON DELETE CASCADE, id TEXT, title TEXT NOT NULL, content TEXT NOT NULL,
 category TEXT NOT NULL, version INT NOT NULL DEFAULT 1, archived BOOLEAN NOT NULL DEFAULT false,
 indexing_status TEXT NOT NULL DEFAULT 'queued', indexing_error TEXT,
 created_at TIMESTAMPTZ NOT NULL DEFAULT now(), updated_at TIMESTAMPTZ NOT NULL DEFAULT now(), PRIMARY KEY(workspace_id,id)
);
CREATE TABLE IF NOT EXISTS knowledge_chunks (
 workspace_id UUID, article_id TEXT, version INT NOT NULL, number INT NOT NULL, content TEXT NOT NULL,
 embedding vector(768), embedding_model TEXT,
 PRIMARY KEY(workspace_id,article_id,version,number),
 FOREIGN KEY(workspace_id,article_id) REFERENCES knowledge(workspace_id,id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS chunks_text ON knowledge_chunks USING GIN(to_tsvector('english',content));
CREATE TABLE IF NOT EXISTS operations (
 workspace_id UUID, study_id TEXT, site_id TEXT, evidence JSONB NOT NULL,
 updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 PRIMARY KEY(workspace_id,study_id,site_id), FOREIGN KEY(workspace_id,site_id,study_id) REFERENCES sites(workspace_id,id,study_id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS runs (
 workspace_id UUID, id UUID, case_id TEXT NOT NULL, result JSONB NOT NULL,
 duration_seconds DOUBLE PRECISION NOT NULL, model TEXT NOT NULL,
 decision TEXT CHECK(decision IN ('approved','rejected')), reviewer_id UUID REFERENCES users ON DELETE SET NULL,
 review_notes TEXT, reviewed_at TIMESTAMPTZ, created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 PRIMARY KEY(workspace_id,id), FOREIGN KEY(workspace_id,case_id) REFERENCES cases(workspace_id,id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS case_events (
 id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY, workspace_id UUID, case_id TEXT NOT NULL,
 run_id UUID, actor_id UUID REFERENCES users ON DELETE SET NULL, actor_name TEXT NOT NULL,
 event_type TEXT NOT NULL, notes TEXT NOT NULL DEFAULT '', payload JSONB NOT NULL DEFAULT '{}',
 created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 FOREIGN KEY(workspace_id,case_id) REFERENCES cases(workspace_id,id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS events_case ON case_events(workspace_id,case_id,id);
CREATE TABLE IF NOT EXISTS jobs (
 id UUID PRIMARY KEY, workspace_id UUID REFERENCES workspaces ON DELETE CASCADE, actor_id UUID REFERENCES users ON DELETE SET NULL,
 kind TEXT NOT NULL CHECK(kind IN ('investigate','index')), target_id TEXT NOT NULL,
 status TEXT NOT NULL DEFAULT 'queued' CHECK(status IN ('queued','running','completed','failed')),
 result_id UUID, error TEXT, attempts INT NOT NULL DEFAULT 0, lease_token UUID,
 created_at TIMESTAMPTZ NOT NULL DEFAULT now(), started_at TIMESTAMPTZ, finished_at TIMESTAMPTZ
);
CREATE UNIQUE INDEX IF NOT EXISTS pending_jobs ON jobs(workspace_id,kind,target_id) WHERE status IN ('queued','running');
CREATE TABLE IF NOT EXISTS roi_scenarios (
 workspace_id UUID, run_id UUID, baseline NUMERIC NOT NULL CHECK(baseline>=0), assisted NUMERIC NOT NULL CHECK(assisted>=0),
 hourly_cost NUMERIC NOT NULL CHECK(hourly_cost>=0), ai_cost NUMERIC NOT NULL CHECK(ai_cost>=0),
 actor_id UUID REFERENCES users ON DELETE SET NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 PRIMARY KEY(workspace_id,run_id), FOREIGN KEY(workspace_id,run_id) REFERENCES runs(workspace_id,id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS feedback (
 id UUID PRIMARY KEY, workspace_id UUID REFERENCES workspaces ON DELETE SET NULL, actor_id UUID REFERENCES users ON DELETE SET NULL,
 rating INT NOT NULL CHECK(rating BETWEEN 1 AND 5), message TEXT NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS rate_limits (
 key TEXT PRIMARY KEY, window_start TIMESTAMPTZ NOT NULL DEFAULT now(), count INT NOT NULL DEFAULT 1
);
