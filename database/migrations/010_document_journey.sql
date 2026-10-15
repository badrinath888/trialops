-- Additive: document journey reconciliation. No existing table is altered. All rows are append-only (revoked_at is the only update, on journey_links).
CREATE TABLE journey_exports (
 workspace_id UUID NOT NULL REFERENCES workspaces ON DELETE CASCADE, id UUID NOT NULL, study_id TEXT NOT NULL, site_id TEXT NOT NULL,
 source_system TEXT NOT NULL, export_ref TEXT NOT NULL, observed_at TIMESTAMPTZ NOT NULL, coverage JSONB NOT NULL, mapping JSONB NOT NULL,
 records JSONB NOT NULL, content_hash TEXT NOT NULL, actor_id UUID REFERENCES users ON DELETE SET NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 PRIMARY KEY(workspace_id,id), UNIQUE(workspace_id,source_system,export_ref),
 FOREIGN KEY(workspace_id,site_id,study_id) REFERENCES sites(workspace_id,id,study_id) ON DELETE CASCADE
);
CREATE TABLE journey_subjects (
 workspace_id UUID NOT NULL, id UUID NOT NULL, case_id TEXT NOT NULL, rev INT NOT NULL, document_system TEXT NOT NULL, document_ref TEXT NOT NULL,
 document_version TEXT NOT NULL, destination_system TEXT NOT NULL, binder_ref TEXT NOT NULL, actor_id UUID REFERENCES users ON DELETE SET NULL,
 actor_name TEXT NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 PRIMARY KEY(workspace_id,id), UNIQUE(workspace_id,case_id,rev), FOREIGN KEY(workspace_id,case_id) REFERENCES cases ON DELETE CASCADE
);
CREATE TABLE journey_links (
 workspace_id UUID NOT NULL, id UUID NOT NULL, case_id TEXT NOT NULL, kind TEXT NOT NULL CHECK(kind IN ('document','record','destination')),
 from_system TEXT NOT NULL, from_ref TEXT NOT NULL, to_system TEXT NOT NULL, to_ref TEXT NOT NULL, rationale TEXT NOT NULL, evidence TEXT NOT NULL,
 actor_id UUID REFERENCES users ON DELETE SET NULL, actor_name TEXT NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 revoked_at TIMESTAMPTZ, revoked_by TEXT, revoke_reason TEXT,
 PRIMARY KEY(workspace_id,id), FOREIGN KEY(workspace_id,case_id) REFERENCES cases ON DELETE CASCADE
);
CREATE TABLE journey_assessments (
 workspace_id UUID NOT NULL, id UUID NOT NULL, case_id TEXT NOT NULL, fingerprint TEXT NOT NULL, subject_rev INT, result JSONB NOT NULL,
 actor_id UUID REFERENCES users ON DELETE SET NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 PRIMARY KEY(workspace_id,id), UNIQUE(workspace_id,case_id,fingerprint), FOREIGN KEY(workspace_id,case_id) REFERENCES cases ON DELETE CASCADE
);
CREATE TABLE journey_plan_items (
 workspace_id UUID NOT NULL, id UUID NOT NULL, case_id TEXT NOT NULL, stage TEXT NOT NULL, gap_key TEXT NOT NULL, assessment_id UUID NOT NULL,
 request_id UUID NOT NULL, contact_id UUID, question TEXT NOT NULL, would_settle TEXT NOT NULL, actor_name TEXT NOT NULL,
 created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 PRIMARY KEY(workspace_id,id), FOREIGN KEY(workspace_id,case_id) REFERENCES cases ON DELETE CASCADE,
 FOREIGN KEY(workspace_id,request_id) REFERENCES information_requests ON DELETE CASCADE,
 FOREIGN KEY(workspace_id,assessment_id) REFERENCES journey_assessments ON DELETE CASCADE
);
CREATE TABLE journey_outcomes (
 workspace_id UUID NOT NULL, id UUID NOT NULL, case_id TEXT NOT NULL, outcome_key UUID NOT NULL, rev INT NOT NULL, description TEXT NOT NULL,
 requirements JSONB, required BOOLEAN NOT NULL DEFAULT true, remediation_at TIMESTAMPTZ, retired BOOLEAN NOT NULL DEFAULT false,
 actor_id UUID REFERENCES users ON DELETE SET NULL, actor_name TEXT NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 PRIMARY KEY(workspace_id,id), UNIQUE(workspace_id,case_id,outcome_key,rev), FOREIGN KEY(workspace_id,case_id) REFERENCES cases ON DELETE CASCADE
);
CREATE TABLE journey_verifications (
 workspace_id UUID NOT NULL, id UUID NOT NULL, case_id TEXT NOT NULL, assessment_id UUID NOT NULL, subject_rev INT, outcomes JSONB NOT NULL,
 human JSONB NOT NULL, results JSONB NOT NULL, overall TEXT NOT NULL CHECK(overall IN ('verified','not_verified','partially_verified','insufficient_evidence')),
 policy JSONB NOT NULL, evaluated_at TIMESTAMPTZ NOT NULL, rationale TEXT NOT NULL, actor_id UUID REFERENCES users ON DELETE SET NULL,
 actor_name TEXT NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 PRIMARY KEY(workspace_id,id), FOREIGN KEY(workspace_id,case_id) REFERENCES cases ON DELETE CASCADE,
 FOREIGN KEY(workspace_id,assessment_id) REFERENCES journey_assessments ON DELETE CASCADE
);
CREATE INDEX journey_exports_scope ON journey_exports(workspace_id,study_id,site_id,observed_at);
CREATE INDEX journey_case_verifications ON journey_verifications(workspace_id,case_id,created_at DESC);
