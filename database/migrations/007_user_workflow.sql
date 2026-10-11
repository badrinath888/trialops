ALTER TABLE workspace_policies ADD COLUMN external_responses_enabled BOOLEAN NOT NULL DEFAULT true;
CREATE TABLE external_response_links (
 workspace_id UUID,id UUID,case_id TEXT NOT NULL,request_id UUID NOT NULL,
 token_hash TEXT NOT NULL UNIQUE,contact_id UUID,created_by UUID REFERENCES users ON DELETE SET NULL,
 question JSONB NOT NULL,expires_at TIMESTAMPTZ NOT NULL,revoked_at TIMESTAMPTZ,
 created_at TIMESTAMPTZ NOT NULL DEFAULT now(),PRIMARY KEY(workspace_id,id),
 FOREIGN KEY(workspace_id,case_id) REFERENCES cases ON DELETE CASCADE,
 FOREIGN KEY(workspace_id,request_id) REFERENCES information_requests ON DELETE CASCADE,
 FOREIGN KEY(workspace_id,contact_id) REFERENCES support_contacts ON DELETE SET NULL (contact_id)
);
CREATE INDEX external_links_request ON external_response_links(workspace_id,request_id);
CREATE TABLE external_responses (
 workspace_id UUID,id UUID,case_id TEXT NOT NULL,request_id UUID NOT NULL,link_id UUID NOT NULL,
 submission_id UUID NOT NULL,text TEXT NOT NULL CHECK(length(text) BETWEEN 10 AND 4000),
 attribution TEXT NOT NULL DEFAULT 'External link holder; identity not verified',
 status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','accepted','clarification')),
 review_reason TEXT,reviewed_by UUID REFERENCES users ON DELETE SET NULL,reviewer_name TEXT,
 submitted_at TIMESTAMPTZ NOT NULL DEFAULT now(),reviewed_at TIMESTAMPTZ,version INT NOT NULL DEFAULT 1,
 PRIMARY KEY(workspace_id,id),UNIQUE(workspace_id,link_id),
 FOREIGN KEY(workspace_id,case_id) REFERENCES cases ON DELETE CASCADE,
 FOREIGN KEY(workspace_id,request_id) REFERENCES information_requests ON DELETE CASCADE,
 FOREIGN KEY(workspace_id,link_id) REFERENCES external_response_links ON DELETE CASCADE
);
