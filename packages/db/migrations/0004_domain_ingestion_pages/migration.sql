-- Persist crawled page structure/content for domain ingestion. The existing
-- crawl_snapshots table records the crawl event; crawl_pages stores the
-- queryable pages captured in that snapshot.

CREATE TABLE crawl_pages (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  domain_id uuid NOT NULL REFERENCES domains(id) ON DELETE CASCADE,
  snapshot_id uuid NOT NULL REFERENCES crawl_snapshots(id) ON DELETE CASCADE,
  ordinal integer NOT NULL,
  url text NOT NULL,
  title text NOT NULL,
  headings jsonb NOT NULL DEFAULT '[]',
  text text NOT NULL,
  meta_description text NOT NULL DEFAULT '',
  has_structured_data boolean NOT NULL DEFAULT false,
  links jsonb NOT NULL DEFAULT '[]',
  captured_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT crawl_pages_snapshot_url_key UNIQUE (snapshot_id, url)
);

CREATE INDEX crawl_pages_org_domain_snapshot_idx ON crawl_pages(org_id, domain_id, snapshot_id);
CREATE INDEX crawl_pages_org_domain_url_idx ON crawl_pages(org_id, domain_id, url);

ALTER TABLE crawl_pages ENABLE ROW LEVEL SECURITY;
ALTER TABLE crawl_pages FORCE ROW LEVEL SECURITY;
CREATE POLICY crawl_pages_tenant_isolation ON crawl_pages
  USING (org_id = app.current_org_id())
  WITH CHECK (org_id = app.current_org_id());
