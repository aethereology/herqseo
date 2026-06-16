CREATE TABLE cms_credentials (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  domain_id uuid NOT NULL REFERENCES domains(id) ON DELETE CASCADE,
  kind "IntegrationKind" NOT NULL,
  encrypted_payload text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT cms_credentials_org_domain_kind_key UNIQUE (org_id, domain_id, kind)
);

CREATE INDEX cms_credentials_org_idx ON cms_credentials(org_id);

ALTER TABLE cms_credentials ENABLE ROW LEVEL SECURITY;
ALTER TABLE cms_credentials FORCE ROW LEVEL SECURITY;
CREATE POLICY cms_credentials_tenant_isolation ON cms_credentials
  USING (org_id = app.current_org_id())
  WITH CHECK (org_id = app.current_org_id());
