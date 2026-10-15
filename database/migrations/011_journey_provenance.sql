-- Additive: provenance for adopted snapshot links, and reviewed-response attestations (context only; never verify on their own).
ALTER TABLE journey_links ADD COLUMN snapshot_decision_id UUID;
CREATE TABLE journey_attestations (
 workspace_id UUID NOT NULL, id UUID NOT NULL, case_id TEXT NOT NULL, response_ref TEXT NOT NULL, response_submitted_at TIMESTAMPTZ NOT NULL,
 response_reviewer TEXT, response_reviewed_at TIMESTAMPTZ, stage TEXT NOT NULL, source_system TEXT NOT NULL, source_ref TEXT NOT NULL,
 document_ref TEXT, version TEXT, transfer_ref TEXT, binder_ref TEXT, status TEXT, observed_at TIMESTAMPTZ NOT NULL, rationale TEXT NOT NULL,
 actor_id UUID REFERENCES users ON DELETE SET NULL, actor_name TEXT NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 PRIMARY KEY(workspace_id,id), FOREIGN KEY(workspace_id,case_id) REFERENCES cases ON DELETE CASCADE
);
