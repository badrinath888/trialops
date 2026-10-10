CREATE TABLE case_assessments (
 workspace_id UUID, id UUID, case_id TEXT NOT NULL,
 kind TEXT NOT NULL CHECK(kind IN ('wording','linkage','questions')),
 actor_id UUID NOT NULL REFERENCES users ON DELETE CASCADE,
 input JSONB NOT NULL, context_hash TEXT NOT NULL, configuration JSONB NOT NULL,
 frozen_evidence JSONB NOT NULL, result JSONB, created_at TIMESTAMPTZ NOT NULL DEFAULT now(), finished_at TIMESTAMPTZ,
 PRIMARY KEY(workspace_id,id), FOREIGN KEY(workspace_id,case_id) REFERENCES cases ON DELETE CASCADE
);
CREATE INDEX assessment_case_history ON case_assessments(workspace_id,case_id,created_at DESC);
CREATE TABLE assessment_decisions (
 workspace_id UUID, id UUID, assessment_id UUID NOT NULL, case_id TEXT NOT NULL,
 actor_id UUID REFERENCES users ON DELETE SET NULL, actor_name TEXT NOT NULL,
 action TEXT NOT NULL CHECK(action IN ('disagree','confirm_link','question_usefulness','request_draft')),
 target TEXT NOT NULL, reason TEXT NOT NULL, details JSONB NOT NULL,
 created_at TIMESTAMPTZ NOT NULL DEFAULT now(), PRIMARY KEY(workspace_id,id),
 FOREIGN KEY(workspace_id,assessment_id) REFERENCES case_assessments ON DELETE CASCADE,
 FOREIGN KEY(workspace_id,case_id) REFERENCES cases ON DELETE CASCADE
);
CREATE UNIQUE INDEX assessment_question_draft ON assessment_decisions(workspace_id,assessment_id,target) WHERE action='request_draft';
ALTER TABLE jobs DROP CONSTRAINT jobs_kind_check;
ALTER TABLE jobs ADD CONSTRAINT jobs_kind_check CHECK(kind IN ('investigate','index','evaluate','assess'));
