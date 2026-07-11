# Data Model

> Postgres with **row-level security** for tenant isolation. Every tenant-scoped table carries `org_id`.
> This is a starting schema — refine in `packages/db` and keep this doc in sync.

## Tenancy hierarchy

```
Organization (tenant root, = billing account)
  └── Users (roles: owner, admin, member)
  └── Domains (the websites/brands being optimized)
        └── everything below is scoped to a domain
```

For the **Agency Partner** tier, an Organization can be an agency that owns many client Domains (and optionally sub-orgs); per-client billing rolls up to the agency.

## Core entities

### Organization
`id, name, plan_tier, stripe_customer_id, token_budget_monthly, token_used_current_period, autonomy_default, created_at`

### User
`id, org_id, email, role, auth_provider_id, created_at`

### Domain
`id, org_id, url, cms_type, cms_credentials_ref, brand_voice_profile_ref, autonomy_mode, status, created_at`

### AgentInstance
`id, domain_id, agent_instance_ref, memory_store_ref, status (provisioning|active|paused), last_run_at`
- One agent per domain. `memory_store_ref` points to that agent's persistent memory.

### CrawlSnapshot
`id, domain_id, captured_at, page_count, storage_ref`
- Point-in-time capture of the site for diffing and context.

### VisibilityCheck
`id, domain_id, engine (chatgpt|aio|gemini|perplexity|claude|copilot|grok|…), prompt, captured_at, brand_cited (bool), citation_rank, sentiment, share_of_voice, raw_response_ref`

### Opportunity
`id, domain_id, type (content|technical|citation), priority, title, rationale, source_prompt, source_engine, source_doc_ref, status (proposed|approved|rejected|in_progress|done), confidence`
- `rationale` + `source_*` fields satisfy the explainability requirement.

### ContentPiece
`id, domain_id, opportunity_id, title, body_ref, schema_json, status (draft|pending_approval|published|failed), cms_post_id, published_at, word_count`

### TechnicalFix
`id, domain_id, opportunity_id, fix_type (schema|internal_link|llms_txt|meta|crawler_access), target_url, diff, status, applied_at`

### CitationCampaign
`id, domain_id, opportunity_id, channel (reddit|youtube|wikipedia|outreach), target, status, outcome`

### ApprovalEvent
`id, domain_id, entity_type, entity_id, action (approve|reject), user_id, note, created_at`
- Audit trail for the autonomy gates.

### ModelUsage  (billing + margin critical)
`id, org_id, domain_id, task_class, provider, model, input_tokens, output_tokens, cost_usd, created_at`
- Written by the metering wrapper on **every** model call. Source of truth for overage billing and margin.

### LiftMeasurement
`id, domain_id, baseline_check_id, followup_check_id, metric, delta, measured_at`

### Integration
`id, org_id, kind (ga4|gsc|hubspot|salesforce|shopify|wordpress|webflow|…), credentials_ref, status, connected_at`

## Indexing & isolation notes
- Composite indexes on `(org_id, domain_id, created_at)` for the high-volume tables (`VisibilityCheck`, `ModelUsage`, `ContentPiece`).
- RLS policy on every tenant table: `org_id = current_setting('app.current_org')::uuid`.
- App code must `SET app.current_org` per request/job; never rely on RLS alone — scope queries explicitly too.
- Credentials are stored as references (`*_ref`) to a secrets vault, never inline.

## Open modeling questions
- Time-series volume for `VisibilityCheck` and `ModelUsage` may warrant partitioning or a TSDB later.
- Agent memory storage format is owned by the agent runtime layer (`agent-runtime-layer.md`); this DB stores only the reference + metadata.
