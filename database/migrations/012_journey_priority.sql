-- Additive: explainable evidence-request prioritization for the Document journey collection plan. Append-only; no existing table altered.
CREATE TABLE journey_priority_inputs (
 workspace_id UUID NOT NULL, id UUID NOT NULL, case_id TEXT NOT NULL, gap_key TEXT NOT NULL, rev INT NOT NULL,
 effort TEXT NOT NULL CHECK(effort IN ('low','medium','high','unknown')), effort_note TEXT NOT NULL DEFAULT '', prerequisites JSONB NOT NULL DEFAULT '[]',
 actor_id UUID REFERENCES users ON DELETE SET NULL, actor_name TEXT NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 PRIMARY KEY(workspace_id,id), UNIQUE(workspace_id,case_id,gap_key,rev), FOREIGN KEY(workspace_id,case_id) REFERENCES cases ON DELETE CASCADE
);
CREATE TABLE journey_priority_mappings (
 workspace_id UUID NOT NULL, id UUID NOT NULL, case_id TEXT NOT NULL, gap_key TEXT NOT NULL, check_key TEXT NOT NULL,
 action TEXT NOT NULL CHECK(action IN ('add','remove','reset')), reason TEXT NOT NULL,
 actor_id UUID REFERENCES users ON DELETE SET NULL, actor_name TEXT NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 PRIMARY KEY(workspace_id,id), FOREIGN KEY(workspace_id,case_id) REFERENCES cases ON DELETE CASCADE
);
CREATE TABLE journey_prioritizations (
 workspace_id UUID NOT NULL, id UUID NOT NULL, case_id TEXT NOT NULL, rev INT NOT NULL, rule_version TEXT NOT NULL, input_hash TEXT NOT NULL,
 inputs JSONB NOT NULL, suggested JSONB NOT NULL, override JSONB, actor_id UUID REFERENCES users ON DELETE SET NULL, actor_name TEXT NOT NULL,
 created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 PRIMARY KEY(workspace_id,id), UNIQUE(workspace_id,case_id,rev), FOREIGN KEY(workspace_id,case_id) REFERENCES cases ON DELETE CASCADE
);
