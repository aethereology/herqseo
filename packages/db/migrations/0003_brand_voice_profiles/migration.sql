-- Cache the brand-voice profile derived from a domain's own site copy, so the
-- operator loop doesn't re-derive it on every run. One profile per domain.

CREATE TABLE brand_voice_profiles (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  domain_id uuid NOT NULL UNIQUE REFERENCES domains(id) ON DELETE CASCADE,
  brand text NOT NULL,
  guidelines text NOT NULL,
  source text NOT NULL DEFAULT 'derived',
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX brand_voice_profiles_org_idx ON brand_voice_profiles(org_id);

ALTER TABLE brand_voice_profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE brand_voice_profiles FORCE ROW LEVEL SECURITY;
CREATE POLICY brand_voice_profiles_tenant_isolation ON brand_voice_profiles
  USING (org_id = app.current_org_id())
  WITH CHECK (org_id = app.current_org_id());
