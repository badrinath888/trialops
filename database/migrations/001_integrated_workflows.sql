CREATE TABLE IF NOT EXISTS workspace_policies (
 workspace_id UUID PRIMARY KEY REFERENCES workspaces ON DELETE CASCADE,
 freshness_hours NUMERIC CHECK(freshness_hours>0), reminder_lead_hours INT NOT NULL DEFAULT 24 CHECK(reminder_lead_hours BETWEEN 0 AND 168),
 reminder_frequency_minutes INT NOT NULL DEFAULT 60 CHECK(reminder_frequency_minutes BETWEEN 15 AND 10080),
 visit_checklist JSONB NOT NULL DEFAULT '[]', version INT NOT NULL DEFAULT 1, updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS procedure_versions (
 workspace_id UUID, article_id TEXT, version INT, title TEXT NOT NULL, content TEXT NOT NULL, category TEXT NOT NULL,
 actor_id UUID REFERENCES users ON DELETE SET NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 PRIMARY KEY(workspace_id,article_id,version), FOREIGN KEY(workspace_id,article_id) REFERENCES knowledge ON DELETE CASCADE
);
INSERT INTO procedure_versions(workspace_id,article_id,version,title,content,category,created_at)
SELECT workspace_id,id,version,title,content,category,updated_at FROM knowledge ON CONFLICT DO NOTHING;
CREATE TABLE IF NOT EXISTS snapshot_history (
 workspace_id UUID, id UUID NOT NULL, study_id TEXT NOT NULL, site_id TEXT NOT NULL, external_id TEXT NOT NULL,
 observed_at TIMESTAMPTZ NOT NULL, evidence JSONB NOT NULL, content_hash TEXT NOT NULL,
 actor_id UUID REFERENCES users ON DELETE SET NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 PRIMARY KEY(workspace_id,id), UNIQUE(workspace_id,study_id,site_id,external_id),
 FOREIGN KEY(workspace_id,site_id,study_id) REFERENCES sites(workspace_id,id,study_id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS investigation_checks (
 workspace_id UUID, id UUID, case_id TEXT NOT NULL, run_id UUID NOT NULL, sources JSONB NOT NULL, items JSONB NOT NULL,
 status TEXT NOT NULL DEFAULT 'draft' CHECK(status IN ('draft','active')), due_at TIMESTAMPTZ,
 version INT NOT NULL DEFAULT 1, actor_id UUID REFERENCES users ON DELETE SET NULL,
 activated_by UUID REFERENCES users ON DELETE SET NULL, activated_at TIMESTAMPTZ,
 created_at TIMESTAMPTZ NOT NULL DEFAULT now(), updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 PRIMARY KEY(workspace_id,id), UNIQUE(workspace_id,run_id),
 FOREIGN KEY(workspace_id,case_id) REFERENCES cases ON DELETE CASCADE,
 FOREIGN KEY(workspace_id,run_id) REFERENCES runs ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS information_requests (
 workspace_id UUID, id UUID, case_id TEXT NOT NULL, run_id UUID NOT NULL, title TEXT NOT NULL, items JSONB NOT NULL,
 owner_id UUID REFERENCES users ON DELETE SET NULL, due_at TIMESTAMPTZ, status TEXT NOT NULL DEFAULT 'draft'
 CHECK(status IN ('draft','requested','received','cancelled')), responses JSONB NOT NULL DEFAULT '[]',
 version INT NOT NULL DEFAULT 1, actor_id UUID REFERENCES users ON DELETE SET NULL,
 created_at TIMESTAMPTZ NOT NULL DEFAULT now(), updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 PRIMARY KEY(workspace_id,id), FOREIGN KEY(workspace_id,case_id) REFERENCES cases ON DELETE CASCADE,
 FOREIGN KEY(workspace_id,run_id) REFERENCES runs ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS case_evidence (
 workspace_id UUID, id UUID, case_id TEXT NOT NULL, kind TEXT NOT NULL CHECK(kind IN ('human_observation','snapshot','request_response')),
 reference_id TEXT, summary TEXT NOT NULL, observed_at TIMESTAMPTZ NOT NULL,
 actor_id UUID REFERENCES users ON DELETE SET NULL, actor_name TEXT NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 PRIMARY KEY(workspace_id,id), FOREIGN KEY(workspace_id,case_id) REFERENCES cases ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS snapshot_comparisons (
 workspace_id UUID, id UUID, case_id TEXT NOT NULL, before_id UUID NOT NULL, after_id UUID NOT NULL,
 comparison JSONB NOT NULL, actor_id UUID REFERENCES users ON DELETE SET NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 PRIMARY KEY(workspace_id,id), UNIQUE(workspace_id,case_id,before_id,after_id),
 FOREIGN KEY(workspace_id,case_id) REFERENCES cases ON DELETE CASCADE,
 FOREIGN KEY(workspace_id,before_id) REFERENCES snapshot_history ON DELETE CASCADE,
 FOREIGN KEY(workspace_id,after_id) REFERENCES snapshot_history ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS case_links (
 workspace_id UUID, case_id TEXT, related_id TEXT, actor_id UUID REFERENCES users ON DELETE SET NULL,
 rationale TEXT NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 PRIMARY KEY(workspace_id,case_id,related_id), CHECK(case_id<related_id),
 FOREIGN KEY(workspace_id,case_id) REFERENCES cases ON DELETE CASCADE,
 FOREIGN KEY(workspace_id,related_id) REFERENCES cases(workspace_id,id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS procedure_reassessments (
 workspace_id UUID, run_id UUID, article_id TEXT, old_version INT, new_version INT, case_id TEXT NOT NULL,
 status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','needed','not_needed')), rationale TEXT,
 reviewer_id UUID REFERENCES users ON DELETE SET NULL, reviewed_at TIMESTAMPTZ, version INT NOT NULL DEFAULT 1,
 created_at TIMESTAMPTZ NOT NULL DEFAULT now(), PRIMARY KEY(workspace_id,run_id,article_id,new_version),
 FOREIGN KEY(workspace_id,run_id) REFERENCES runs ON DELETE CASCADE,
 FOREIGN KEY(workspace_id,case_id) REFERENCES cases ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS human_effort (
 workspace_id UUID, id UUID, case_id TEXT NOT NULL, run_id UUID, minutes NUMERIC NOT NULL CHECK(minutes>0 AND minutes<=1440),
 activity TEXT NOT NULL, notes TEXT NOT NULL, actor_id UUID REFERENCES users ON DELETE SET NULL, recorded_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 PRIMARY KEY(workspace_id,id), FOREIGN KEY(workspace_id,case_id) REFERENCES cases ON DELETE CASCADE,
 FOREIGN KEY(workspace_id,run_id) REFERENCES runs ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS monitoring_visits (
 workspace_id UUID, id UUID, study_id TEXT NOT NULL, site_id TEXT NOT NULL, visit_at TIMESTAMPTZ NOT NULL,
 title TEXT NOT NULL, checklist JSONB NOT NULL, version INT NOT NULL DEFAULT 1,
 actor_id UUID REFERENCES users ON DELETE SET NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT now(), updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 PRIMARY KEY(workspace_id,id), FOREIGN KEY(workspace_id,site_id,study_id) REFERENCES sites(workspace_id,id,study_id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS notification_preferences (
 workspace_id UUID REFERENCES workspaces ON DELETE CASCADE, user_id UUID REFERENCES users ON DELETE CASCADE,
 enabled BOOLEAN NOT NULL DEFAULT true, kinds JSONB NOT NULL DEFAULT '["request","check","reassessment","deadline"]',
 PRIMARY KEY(workspace_id,user_id)
);
CREATE TABLE IF NOT EXISTS notifications (
 workspace_id UUID REFERENCES workspaces ON DELETE CASCADE, user_id UUID REFERENCES users ON DELETE CASCADE,
 id UUID NOT NULL, dedupe_key TEXT NOT NULL, kind TEXT NOT NULL, title TEXT NOT NULL, case_id TEXT NOT NULL,
 read_at TIMESTAMPTZ, created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 PRIMARY KEY(workspace_id,id), UNIQUE(workspace_id,user_id,dedupe_key),
 FOREIGN KEY(workspace_id,case_id) REFERENCES cases ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS reminder_scans (
 workspace_id UUID PRIMARY KEY REFERENCES workspaces ON DELETE CASCADE, last_scan_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS import_previews (
 workspace_id UUID REFERENCES workspaces ON DELETE CASCADE, id UUID, actor_id UUID REFERENCES users ON DELETE CASCADE,
 format TEXT NOT NULL, content_hash TEXT NOT NULL, accepted JSONB NOT NULL, rejected JSONB NOT NULL,
 committed_at TIMESTAMPTZ, expires_at TIMESTAMPTZ NOT NULL DEFAULT now()+interval '1 day', created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 PRIMARY KEY(workspace_id,id)
);
CREATE TABLE IF NOT EXISTS evaluation_runs (
 workspace_id UUID REFERENCES workspaces ON DELETE CASCADE, id UUID, dataset_version TEXT NOT NULL,
 model TEXT NOT NULL, configuration JSONB NOT NULL, results JSONB, actor_id UUID REFERENCES users ON DELETE SET NULL,
 judgment TEXT, judgment_by UUID REFERENCES users ON DELETE SET NULL, judged_at TIMESTAMPTZ,
 created_at TIMESTAMPTZ NOT NULL DEFAULT now(), finished_at TIMESTAMPTZ,
 PRIMARY KEY(workspace_id,id)
);
CREATE TABLE IF NOT EXISTS walkthrough_progress (
 workspace_id UUID REFERENCES workspaces ON DELETE CASCADE, user_id UUID REFERENCES users ON DELETE CASCADE,
 step INT NOT NULL DEFAULT 0 CHECK(step BETWEEN 0 AND 6), skipped BOOLEAN NOT NULL DEFAULT false,
 updated_at TIMESTAMPTZ NOT NULL DEFAULT now(), PRIMARY KEY(workspace_id,user_id)
);
ALTER TABLE jobs DROP CONSTRAINT IF EXISTS jobs_kind_check;
ALTER TABLE jobs ADD CONSTRAINT jobs_kind_check CHECK(kind IN ('investigate','index','evaluate'));
CREATE INDEX IF NOT EXISTS snapshot_scope_time ON snapshot_history(workspace_id,study_id,site_id,observed_at);
CREATE INDEX IF NOT EXISTS requests_due ON information_requests(workspace_id,status,due_at);
CREATE INDEX IF NOT EXISTS notifications_user ON notifications(workspace_id,user_id,created_at DESC);
