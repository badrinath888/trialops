ALTER TABLE cases ADD COLUMN IF NOT EXISTS submission_id UUID;
CREATE UNIQUE INDEX IF NOT EXISTS case_submissions ON cases(workspace_id,submission_id) WHERE submission_id IS NOT NULL;
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS lease_expires_at TIMESTAMPTZ;
