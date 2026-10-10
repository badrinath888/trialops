-- Workspace deletion/purge may cascade through contacts before nested case rows.
-- Clear only the optional contact ID; preserve workspace keys and case history.
ALTER TABLE case_blockers DROP CONSTRAINT case_blockers_workspace_id_contact_id_fkey;
ALTER TABLE case_blockers ADD FOREIGN KEY(workspace_id,contact_id) REFERENCES support_contacts ON DELETE SET NULL (contact_id);
ALTER TABLE information_requests DROP CONSTRAINT information_requests_workspace_id_contact_id_fkey;
ALTER TABLE information_requests ADD FOREIGN KEY(workspace_id,contact_id) REFERENCES support_contacts ON DELETE SET NULL (contact_id);
ALTER TABLE support_contact_events DROP CONSTRAINT support_contact_events_workspace_id_contact_id_fkey;
ALTER TABLE support_contact_events ADD FOREIGN KEY(workspace_id,contact_id) REFERENCES support_contacts ON DELETE CASCADE;
