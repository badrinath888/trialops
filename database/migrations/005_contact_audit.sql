-- Directory edits have no case ID; preserve the existing case audit constraint.
CREATE TABLE support_contact_events (
 id BIGSERIAL PRIMARY KEY,workspace_id UUID REFERENCES workspaces ON DELETE CASCADE,
 contact_id UUID NOT NULL,actor_id UUID REFERENCES users ON DELETE SET NULL,
 actor_name TEXT NOT NULL,event_type TEXT NOT NULL,payload JSONB NOT NULL,
 created_at TIMESTAMPTZ NOT NULL DEFAULT now(),FOREIGN KEY(workspace_id,contact_id) REFERENCES support_contacts
);
