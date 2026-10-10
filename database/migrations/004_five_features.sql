ALTER TABLE users ADD COLUMN email_verified_at TIMESTAMPTZ;
CREATE TABLE account_tokens (
 token_hash TEXT PRIMARY KEY, user_id UUID NOT NULL REFERENCES users ON DELETE CASCADE,
 purpose TEXT NOT NULL CHECK(purpose IN ('reset','verify')), expires_at TIMESTAMPTZ NOT NULL,
 used_at TIMESTAMPTZ, created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX account_token_user ON account_tokens(user_id,purpose);
CREATE TABLE account_events (
 id BIGSERIAL PRIMARY KEY,user_id UUID REFERENCES users ON DELETE CASCADE,
 kind TEXT NOT NULL,created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE support_contacts (
 workspace_id UUID REFERENCES workspaces ON DELETE CASCADE,id UUID,
 study_id TEXT,site_id TEXT,category TEXT NOT NULL,name TEXT NOT NULL,
 primary_contact TEXT NOT NULL,backup_contact TEXT NOT NULL DEFAULT '',escalation_route TEXT NOT NULL DEFAULT '',
 archived BOOLEAN NOT NULL DEFAULT false,version INT NOT NULL DEFAULT 1,
 actor_id UUID REFERENCES users ON DELETE SET NULL,created_at TIMESTAMPTZ NOT NULL DEFAULT now(),updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 PRIMARY KEY(workspace_id,id),FOREIGN KEY(workspace_id,study_id) REFERENCES studies,
 FOREIGN KEY(workspace_id,site_id) REFERENCES sites
);
CREATE TABLE case_handovers (
 workspace_id UUID,id UUID,case_id TEXT NOT NULL,sender_id UUID REFERENCES users ON DELETE SET NULL,
 recipient_id UUID NOT NULL REFERENCES users ON DELETE CASCADE,owner_at_creation UUID,
 reason TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','accepted','declined','cancelled')),
 summary JSONB NOT NULL,decision_reason TEXT,decided_by UUID REFERENCES users ON DELETE SET NULL,
 created_at TIMESTAMPTZ NOT NULL DEFAULT now(),decided_at TIMESTAMPTZ,
 PRIMARY KEY(workspace_id,id),FOREIGN KEY(workspace_id,case_id) REFERENCES cases ON DELETE CASCADE
);
CREATE UNIQUE INDEX case_pending_handover ON case_handovers(workspace_id,case_id) WHERE status='pending';
CREATE TABLE case_blockers (
 workspace_id UUID,id UUID,case_id TEXT NOT NULL,waiting_on TEXT NOT NULL,reason TEXT NOT NULL,
 responsible_id UUID REFERENCES users ON DELETE SET NULL,contact_id UUID,
 started_at TIMESTAMPTZ NOT NULL,follow_up_at TIMESTAMPTZ NOT NULL,cleared_at TIMESTAMPTZ,clear_reason TEXT,
 actor_id UUID REFERENCES users ON DELETE SET NULL,cleared_by UUID REFERENCES users ON DELETE SET NULL,
 created_at TIMESTAMPTZ NOT NULL DEFAULT now(),PRIMARY KEY(workspace_id,id),
 FOREIGN KEY(workspace_id,case_id) REFERENCES cases ON DELETE CASCADE,
 FOREIGN KEY(workspace_id,contact_id) REFERENCES support_contacts
);
CREATE INDEX blockers_due ON case_blockers(workspace_id,follow_up_at) WHERE cleared_at IS NULL;
ALTER TABLE information_requests ADD COLUMN contact_id UUID;
ALTER TABLE information_requests ADD COLUMN duplicate_reason TEXT NOT NULL DEFAULT '';
ALTER TABLE information_requests ADD FOREIGN KEY(workspace_id,contact_id) REFERENCES support_contacts;
