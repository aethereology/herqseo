-- Runtime persistence: let content_pieces round-trip the agent's draft state
-- (inline body + review/cost/model fields for M0, before a secrets/blob vault
-- exists) and add a generic audit_events log for the operator action trail.

-- body_ref was NOT NULL (a future vault reference); M0 stores the body inline,
-- so relax it and add the inline + review/cost columns.
-- The content lifecycle has explicit approve/reject states (Review mode) that
-- the initial ContentStatus enum was missing.
ALTER TYPE "ContentStatus" ADD VALUE IF NOT EXISTS 'approved' AFTER 'pending_approval';
ALTER TYPE "ContentStatus" ADD VALUE IF NOT EXISTS 'rejected' AFTER 'approved';

ALTER TABLE content_pieces ALTER COLUMN body_ref DROP NOT NULL;
ALTER TABLE content_pieces ADD COLUMN body text;
ALTER TABLE content_pieces ADD COLUMN model text;
ALTER TABLE content_pieces ADD COLUMN usage_record_id uuid;
ALTER TABLE content_pieces ADD COLUMN cost_usd numeric(12, 6);
ALTER TABLE content_pieces ADD COLUMN reviewer text;
ALTER TABLE content_pieces ADD COLUMN review_note text;

CREATE TABLE audit_events (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  domain_id uuid NOT NULL REFERENCES domains(id) ON DELETE CASCADE,
  entity_type text NOT NULL,
  entity_id text NOT NULL,
  action text NOT NULL,
  actor text NOT NULL,
  metadata jsonb NOT NULL DEFAULT '{}',
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX audit_events_org_domain_created_idx ON audit_events(org_id, domain_id, created_at);

ALTER TABLE audit_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit_events FORCE ROW LEVEL SECURITY;
CREATE POLICY audit_events_tenant_isolation ON audit_events
  USING (org_id = app.current_org_id())
  WITH CHECK (org_id = app.current_org_id());
