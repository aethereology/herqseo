CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE SCHEMA IF NOT EXISTS app;

CREATE OR REPLACE FUNCTION app.current_org_id()
RETURNS uuid
LANGUAGE sql
STABLE
AS $$
  SELECT NULLIF(current_setting('app.current_org', true), '')::uuid
$$;

CREATE TYPE "PlanTier" AS ENUM ('operator', 'growth', 'scale', 'agency', 'enterprise');
CREATE TYPE "AutonomyMode" AS ENUM ('review', 'auto_publish', 'autopilot');
CREATE TYPE "UserRole" AS ENUM ('owner', 'admin', 'member');
CREATE TYPE "CmsType" AS ENUM ('wordpress', 'webflow', 'contentful', 'sanity', 'shopify');
CREATE TYPE "DomainStatus" AS ENUM ('onboarding', 'active', 'paused');
CREATE TYPE "AgentStatus" AS ENUM ('provisioning', 'active', 'paused', 'failed');
CREATE TYPE "AiEngine" AS ENUM (
  'chatgpt',
  'google_ai_overviews',
  'google_ai_mode',
  'gemini',
  'perplexity',
  'claude',
  'copilot',
  'grok'
);
CREATE TYPE "OpportunityType" AS ENUM ('content', 'technical', 'citation');
CREATE TYPE "OpportunityStatus" AS ENUM ('proposed', 'approved', 'rejected', 'in_progress', 'done');
CREATE TYPE "ContentStatus" AS ENUM ('draft', 'pending_approval', 'published', 'failed');
CREATE TYPE "TechnicalFixType" AS ENUM ('schema', 'internal_link', 'llms_txt', 'meta', 'crawler_access');
CREATE TYPE "TechnicalFixStatus" AS ENUM ('proposed', 'approved', 'applied', 'failed');
CREATE TYPE "CitationChannel" AS ENUM ('reddit', 'youtube', 'wikipedia', 'outreach');
CREATE TYPE "CitationStatus" AS ENUM ('proposed', 'approved', 'in_progress', 'placed', 'failed');
CREATE TYPE "ApprovalAction" AS ENUM ('approve', 'reject');
CREATE TYPE "IntegrationKind" AS ENUM ('ga4', 'gsc', 'hubspot', 'salesforce', 'shopify', 'wordpress', 'webflow');
CREATE TYPE "IntegrationStatus" AS ENUM ('connected', 'disconnected', 'error');

CREATE TABLE organizations (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  name text NOT NULL,
  plan_tier "PlanTier" NOT NULL DEFAULT 'operator',
  stripe_customer_id text,
  token_budget_monthly integer NOT NULL DEFAULT 1000000,
  token_used_current_period integer NOT NULL DEFAULT 0,
  autonomy_default "AutonomyMode" NOT NULL DEFAULT 'review',
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE users (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  email text NOT NULL,
  role "UserRole" NOT NULL DEFAULT 'member',
  auth_provider_id text,
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT users_org_email_key UNIQUE (org_id, email)
);

CREATE TABLE domains (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  url text NOT NULL,
  cms_type "CmsType" NOT NULL,
  cms_credentials_ref text,
  brand_voice_profile_ref text,
  autonomy_mode "AutonomyMode" NOT NULL DEFAULT 'review',
  status "DomainStatus" NOT NULL DEFAULT 'onboarding',
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT domains_org_url_key UNIQUE (org_id, url)
);

CREATE TABLE agent_instances (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  domain_id uuid NOT NULL UNIQUE REFERENCES domains(id) ON DELETE CASCADE,
  hermes_instance_ref text,
  memory_store_ref text NOT NULL,
  status "AgentStatus" NOT NULL DEFAULT 'provisioning',
  last_run_at timestamptz
);

CREATE TABLE crawl_snapshots (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  domain_id uuid NOT NULL REFERENCES domains(id) ON DELETE CASCADE,
  captured_at timestamptz NOT NULL DEFAULT now(),
  page_count integer NOT NULL,
  storage_ref text NOT NULL
);

CREATE TABLE visibility_checks (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  domain_id uuid NOT NULL REFERENCES domains(id) ON DELETE CASCADE,
  engine "AiEngine" NOT NULL,
  prompt text NOT NULL,
  captured_at timestamptz NOT NULL DEFAULT now(),
  brand_cited boolean NOT NULL DEFAULT false,
  citation_rank integer,
  sentiment text,
  share_of_voice numeric(8, 4),
  raw_response_ref text NOT NULL
);

CREATE TABLE opportunities (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  domain_id uuid NOT NULL REFERENCES domains(id) ON DELETE CASCADE,
  type "OpportunityType" NOT NULL,
  priority integer NOT NULL,
  title text NOT NULL,
  rationale text NOT NULL,
  source_prompt text,
  source_engine "AiEngine",
  source_doc_ref text,
  status "OpportunityStatus" NOT NULL DEFAULT 'proposed',
  confidence numeric(5, 4)
);

CREATE TABLE content_pieces (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  domain_id uuid NOT NULL REFERENCES domains(id) ON DELETE CASCADE,
  opportunity_id uuid REFERENCES opportunities(id) ON DELETE SET NULL,
  title text NOT NULL,
  body_ref text NOT NULL,
  schema_json jsonb,
  status "ContentStatus" NOT NULL DEFAULT 'draft',
  cms_post_id text,
  published_at timestamptz,
  word_count integer NOT NULL DEFAULT 0
);

CREATE TABLE technical_fixes (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  domain_id uuid NOT NULL REFERENCES domains(id) ON DELETE CASCADE,
  opportunity_id uuid REFERENCES opportunities(id) ON DELETE SET NULL,
  fix_type "TechnicalFixType" NOT NULL,
  target_url text NOT NULL,
  diff jsonb NOT NULL,
  status "TechnicalFixStatus" NOT NULL DEFAULT 'proposed',
  applied_at timestamptz
);

CREATE TABLE citation_campaigns (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  domain_id uuid NOT NULL REFERENCES domains(id) ON DELETE CASCADE,
  opportunity_id uuid REFERENCES opportunities(id) ON DELETE SET NULL,
  channel "CitationChannel" NOT NULL,
  target text NOT NULL,
  status "CitationStatus" NOT NULL DEFAULT 'proposed',
  outcome text
);

CREATE TABLE approval_events (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  domain_id uuid NOT NULL REFERENCES domains(id) ON DELETE CASCADE,
  entity_type text NOT NULL,
  entity_id uuid NOT NULL,
  action "ApprovalAction" NOT NULL,
  user_id uuid NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
  note text,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE model_usage (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  domain_id uuid NOT NULL REFERENCES domains(id) ON DELETE CASCADE,
  task_class text NOT NULL,
  provider text NOT NULL,
  model text NOT NULL,
  input_tokens integer NOT NULL,
  output_tokens integer NOT NULL,
  cost_usd numeric(12, 6) NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE lift_measurements (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  domain_id uuid NOT NULL REFERENCES domains(id) ON DELETE CASCADE,
  baseline_check_id uuid NOT NULL,
  followup_check_id uuid NOT NULL,
  metric text NOT NULL,
  delta numeric(10, 4) NOT NULL,
  measured_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE integrations (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  kind "IntegrationKind" NOT NULL,
  credentials_ref text NOT NULL,
  status "IntegrationStatus" NOT NULL DEFAULT 'disconnected',
  connected_at timestamptz,
  CONSTRAINT integrations_org_kind_key UNIQUE (org_id, kind)
);

CREATE INDEX users_org_idx ON users(org_id);
CREATE INDEX domains_org_idx ON domains(org_id);
CREATE INDEX agent_instances_org_idx ON agent_instances(org_id);
CREATE INDEX crawl_snapshots_org_domain_captured_idx ON crawl_snapshots(org_id, domain_id, captured_at);
CREATE INDEX visibility_checks_org_domain_captured_idx ON visibility_checks(org_id, domain_id, captured_at);
CREATE INDEX opportunities_org_domain_status_idx ON opportunities(org_id, domain_id, status);
CREATE INDEX content_pieces_org_domain_status_idx ON content_pieces(org_id, domain_id, status);
CREATE INDEX technical_fixes_org_domain_status_idx ON technical_fixes(org_id, domain_id, status);
CREATE INDEX citation_campaigns_org_domain_status_idx ON citation_campaigns(org_id, domain_id, status);
CREATE INDEX approval_events_org_domain_created_idx ON approval_events(org_id, domain_id, created_at);
CREATE INDEX model_usage_org_domain_created_idx ON model_usage(org_id, domain_id, created_at);
CREATE INDEX lift_measurements_org_domain_measured_idx ON lift_measurements(org_id, domain_id, measured_at);
CREATE INDEX integrations_org_idx ON integrations(org_id);

ALTER TABLE organizations ENABLE ROW LEVEL SECURITY;
ALTER TABLE organizations FORCE ROW LEVEL SECURITY;
CREATE POLICY organizations_tenant_isolation ON organizations
  USING (id = app.current_org_id())
  WITH CHECK (id = app.current_org_id());

ALTER TABLE users ENABLE ROW LEVEL SECURITY;
ALTER TABLE users FORCE ROW LEVEL SECURITY;
CREATE POLICY users_tenant_isolation ON users
  USING (org_id = app.current_org_id())
  WITH CHECK (org_id = app.current_org_id());

ALTER TABLE domains ENABLE ROW LEVEL SECURITY;
ALTER TABLE domains FORCE ROW LEVEL SECURITY;
CREATE POLICY domains_tenant_isolation ON domains
  USING (org_id = app.current_org_id())
  WITH CHECK (org_id = app.current_org_id());

ALTER TABLE agent_instances ENABLE ROW LEVEL SECURITY;
ALTER TABLE agent_instances FORCE ROW LEVEL SECURITY;
CREATE POLICY agent_instances_tenant_isolation ON agent_instances
  USING (org_id = app.current_org_id())
  WITH CHECK (org_id = app.current_org_id());

ALTER TABLE crawl_snapshots ENABLE ROW LEVEL SECURITY;
ALTER TABLE crawl_snapshots FORCE ROW LEVEL SECURITY;
CREATE POLICY crawl_snapshots_tenant_isolation ON crawl_snapshots
  USING (org_id = app.current_org_id())
  WITH CHECK (org_id = app.current_org_id());

ALTER TABLE visibility_checks ENABLE ROW LEVEL SECURITY;
ALTER TABLE visibility_checks FORCE ROW LEVEL SECURITY;
CREATE POLICY visibility_checks_tenant_isolation ON visibility_checks
  USING (org_id = app.current_org_id())
  WITH CHECK (org_id = app.current_org_id());

ALTER TABLE opportunities ENABLE ROW LEVEL SECURITY;
ALTER TABLE opportunities FORCE ROW LEVEL SECURITY;
CREATE POLICY opportunities_tenant_isolation ON opportunities
  USING (org_id = app.current_org_id())
  WITH CHECK (org_id = app.current_org_id());

ALTER TABLE content_pieces ENABLE ROW LEVEL SECURITY;
ALTER TABLE content_pieces FORCE ROW LEVEL SECURITY;
CREATE POLICY content_pieces_tenant_isolation ON content_pieces
  USING (org_id = app.current_org_id())
  WITH CHECK (org_id = app.current_org_id());

ALTER TABLE technical_fixes ENABLE ROW LEVEL SECURITY;
ALTER TABLE technical_fixes FORCE ROW LEVEL SECURITY;
CREATE POLICY technical_fixes_tenant_isolation ON technical_fixes
  USING (org_id = app.current_org_id())
  WITH CHECK (org_id = app.current_org_id());

ALTER TABLE citation_campaigns ENABLE ROW LEVEL SECURITY;
ALTER TABLE citation_campaigns FORCE ROW LEVEL SECURITY;
CREATE POLICY citation_campaigns_tenant_isolation ON citation_campaigns
  USING (org_id = app.current_org_id())
  WITH CHECK (org_id = app.current_org_id());

ALTER TABLE approval_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE approval_events FORCE ROW LEVEL SECURITY;
CREATE POLICY approval_events_tenant_isolation ON approval_events
  USING (org_id = app.current_org_id())
  WITH CHECK (org_id = app.current_org_id());

ALTER TABLE model_usage ENABLE ROW LEVEL SECURITY;
ALTER TABLE model_usage FORCE ROW LEVEL SECURITY;
CREATE POLICY model_usage_tenant_isolation ON model_usage
  USING (org_id = app.current_org_id())
  WITH CHECK (org_id = app.current_org_id());

ALTER TABLE lift_measurements ENABLE ROW LEVEL SECURITY;
ALTER TABLE lift_measurements FORCE ROW LEVEL SECURITY;
CREATE POLICY lift_measurements_tenant_isolation ON lift_measurements
  USING (org_id = app.current_org_id())
  WITH CHECK (org_id = app.current_org_id());

ALTER TABLE integrations ENABLE ROW LEVEL SECURITY;
ALTER TABLE integrations FORCE ROW LEVEL SECURITY;
CREATE POLICY integrations_tenant_isolation ON integrations
  USING (org_id = app.current_org_id())
  WITH CHECK (org_id = app.current_org_id());
