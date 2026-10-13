-- Additive: recurrence/prevention, readiness tracker, procedure impact reviews, bulk batches, feedback triage. No existing table is altered.
CREATE TABLE improvement_events (
 workspace_id UUID NOT NULL REFERENCES workspaces ON DELETE CASCADE, id UUID NOT NULL, scope TEXT NOT NULL, ref_id TEXT NOT NULL, kind TEXT NOT NULL,
 actor_id UUID REFERENCES users ON DELETE SET NULL, actor_name TEXT NOT NULL, payload JSONB NOT NULL DEFAULT '{}', created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 PRIMARY KEY(workspace_id,id)
);
CREATE INDEX improvement_events_ref ON improvement_events(workspace_id,scope,ref_id,created_at);
CREATE TABLE recurrence_groups (
 workspace_id UUID NOT NULL REFERENCES workspaces ON DELETE CASCADE, id UUID NOT NULL, title TEXT NOT NULL, category TEXT NOT NULL, study_id TEXT NOT NULL, site_id TEXT,
 basis TEXT NOT NULL CHECK(basis IN ('category_study_site','explicit_links','reviewer_selected')), pattern TEXT NOT NULL,
 status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active','closed')), version INT NOT NULL DEFAULT 1,
 created_by UUID REFERENCES users ON DELETE SET NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT now(), updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 PRIMARY KEY(workspace_id,id)
);
CREATE TABLE recurrence_members (
 workspace_id UUID NOT NULL, id UUID NOT NULL, group_id UUID NOT NULL, case_id TEXT NOT NULL, added_by UUID REFERENCES users ON DELETE SET NULL, added_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 removed_by UUID REFERENCES users ON DELETE SET NULL, removed_at TIMESTAMPTZ, removal_reason TEXT,
 PRIMARY KEY(workspace_id,id), FOREIGN KEY(workspace_id,group_id) REFERENCES recurrence_groups ON DELETE CASCADE,
 FOREIGN KEY(workspace_id,case_id) REFERENCES cases ON DELETE CASCADE
);
CREATE UNIQUE INDEX recurrence_members_active ON recurrence_members(workspace_id,group_id,case_id) WHERE removed_at IS NULL;
CREATE INDEX recurrence_members_case ON recurrence_members(workspace_id,case_id);
CREATE TABLE prevention_plans (
 workspace_id UUID NOT NULL, id UUID NOT NULL, group_id UUID NOT NULL, title TEXT NOT NULL, summary TEXT NOT NULL DEFAULT '',
 status TEXT NOT NULL DEFAULT 'draft' CHECK(status IN ('draft','active','completed')), version INT NOT NULL DEFAULT 1, completion_note TEXT,
 created_by UUID REFERENCES users ON DELETE SET NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT now(), updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 activated_at TIMESTAMPTZ, completed_at TIMESTAMPTZ, PRIMARY KEY(workspace_id,id), FOREIGN KEY(workspace_id,group_id) REFERENCES recurrence_groups ON DELETE CASCADE
);
CREATE TABLE prevention_actions (
 workspace_id UUID NOT NULL, id UUID NOT NULL, plan_id UUID NOT NULL, text TEXT NOT NULL, owner_id UUID REFERENCES users ON DELETE SET NULL, due_at TIMESTAMPTZ,
 status TEXT NOT NULL DEFAULT 'open' CHECK(status IN ('open','done')), evidence JSONB NOT NULL DEFAULT '[]', removed BOOLEAN NOT NULL DEFAULT false,
 done_at TIMESTAMPTZ, position INT NOT NULL DEFAULT 0, PRIMARY KEY(workspace_id,id), FOREIGN KEY(workspace_id,plan_id) REFERENCES prevention_plans ON DELETE CASCADE
);
CREATE TABLE recurrence_windows (
 workspace_id UUID NOT NULL, id UUID NOT NULL, group_id UUID NOT NULL, label TEXT NOT NULL, role TEXT NOT NULL CHECK(role IN ('baseline','follow_up')),
 start_at TIMESTAMPTZ NOT NULL, end_at TIMESTAMPTZ NOT NULL CHECK(end_at>start_at), exposure_count NUMERIC CHECK(exposure_count IS NULL OR exposure_count>0), exposure_unit TEXT,
 created_by UUID REFERENCES users ON DELETE SET NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 PRIMARY KEY(workspace_id,id), FOREIGN KEY(workspace_id,group_id) REFERENCES recurrence_groups ON DELETE CASCADE
);
CREATE TABLE readiness_requirements (
 workspace_id UUID NOT NULL REFERENCES workspaces ON DELETE CASCADE, id UUID NOT NULL, study_id TEXT NOT NULL, site_id TEXT, name TEXT NOT NULL, guidance TEXT NOT NULL DEFAULT '',
 requires_expiry BOOLEAN NOT NULL DEFAULT false, archived BOOLEAN NOT NULL DEFAULT false, version INT NOT NULL DEFAULT 1,
 created_by UUID REFERENCES users ON DELETE SET NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT now(), updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 PRIMARY KEY(workspace_id,id)
);
CREATE TABLE readiness_records (
 workspace_id UUID NOT NULL, id UUID NOT NULL, requirement_id UUID NOT NULL, study_id TEXT NOT NULL, site_id TEXT NOT NULL, requirement_version INT NOT NULL,
 applicable BOOLEAN NOT NULL DEFAULT true, applicability_reason TEXT NOT NULL DEFAULT '', document_identity TEXT NOT NULL DEFAULT '', document_version TEXT NOT NULL DEFAULT '',
 expiry_date DATE, as_of DATE, evidence JSONB NOT NULL DEFAULT '[]', review_status TEXT NOT NULL DEFAULT 'not_reviewed' CHECK(review_status IN ('not_reviewed','awaiting_review','reviewed')),
 reviewer_id UUID REFERENCES users ON DELETE SET NULL, reviewed_at TIMESTAMPTZ, version INT NOT NULL DEFAULT 1,
 recorded_by UUID REFERENCES users ON DELETE SET NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT now(), updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 PRIMARY KEY(workspace_id,id), UNIQUE(workspace_id,requirement_id,site_id), FOREIGN KEY(workspace_id,requirement_id) REFERENCES readiness_requirements ON DELETE CASCADE
);
CREATE TABLE procedure_impact_reviews (
 workspace_id UUID NOT NULL, id UUID NOT NULL, article_id TEXT NOT NULL, old_version INT NOT NULL, new_version INT NOT NULL,
 status TEXT NOT NULL CHECK(status IN ('needed','not_needed')), rationale TEXT NOT NULL, reviewer_id UUID REFERENCES users ON DELETE SET NULL, reviewed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 version INT NOT NULL DEFAULT 1, comparison_hash TEXT NOT NULL, PRIMARY KEY(workspace_id,id), UNIQUE(workspace_id,article_id,old_version,new_version),
 FOREIGN KEY(workspace_id,article_id) REFERENCES knowledge ON DELETE CASCADE
);
CREATE TABLE bulk_batches (
 workspace_id UUID NOT NULL REFERENCES workspaces ON DELETE CASCADE, id UUID NOT NULL, actor_id UUID REFERENCES users ON DELETE SET NULL, request JSONB NOT NULL, results JSONB NOT NULL,
 created_at TIMESTAMPTZ NOT NULL DEFAULT now(), PRIMARY KEY(workspace_id,id)
);
CREATE TABLE improvements (
 workspace_id UUID NOT NULL REFERENCES workspaces ON DELETE CASCADE, id UUID NOT NULL, title TEXT NOT NULL, description TEXT NOT NULL DEFAULT '',
 status TEXT NOT NULL DEFAULT 'planned' CHECK(status IN ('planned','in_progress','completed','declined')), owner_id UUID REFERENCES users ON DELETE SET NULL, explanation TEXT NOT NULL DEFAULT '',
 version INT NOT NULL DEFAULT 1, created_by UUID REFERENCES users ON DELETE SET NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT now(), updated_at TIMESTAMPTZ NOT NULL DEFAULT now(), completed_at TIMESTAMPTZ,
 PRIMARY KEY(workspace_id,id)
);
CREATE TABLE feedback_triage (
 workspace_id UUID NOT NULL REFERENCES workspaces ON DELETE CASCADE, feedback_id UUID NOT NULL REFERENCES feedback ON DELETE CASCADE,
 status TEXT NOT NULL DEFAULT 'received' CHECK(status IN ('received','reviewing','planned','in_progress','completed','declined')),
 owner_id UUID REFERENCES users ON DELETE SET NULL, internal_note TEXT NOT NULL DEFAULT '', public_note TEXT NOT NULL DEFAULT '', confidential BOOLEAN NOT NULL DEFAULT false,
 improvement_id UUID, related_feedback JSONB NOT NULL DEFAULT '[]', version INT NOT NULL DEFAULT 1,
 created_at TIMESTAMPTZ NOT NULL DEFAULT now(), updated_at TIMESTAMPTZ NOT NULL DEFAULT now(), status_changed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 PRIMARY KEY(workspace_id,feedback_id), FOREIGN KEY(workspace_id,improvement_id) REFERENCES improvements
);
