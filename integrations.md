# Integrations

> Document every integration here as you build it: auth method, scopes, key endpoints, gotchas.
> All credentials stored as vault references (`*_ref`), never inline. One connector interface in `packages/integrations`.

## Connector interface (target shape)

Each connector implements a common contract so the agent/orchestration layer treats them uniformly:

```
connect(orgId, config) -> Integration
verify() -> healthy | error
read(...)   // pull data (analytics, rankings, content)
write(...)  // push changes (publish content, apply fixes) — gated by autonomy mode
```

Writes always pass through the autonomy/guardrail layer before reaching a customer system.

## CMS connectors (publishing targets)

### WordPress  — **Phase 1, first**
- Auth: application passwords or OAuth via a QueryClear plugin.
- Capabilities: create/update posts & pages, inject schema, manage internal links, edit meta.
- Gotcha: hosting variance; confirm REST API availability and auth flow per site during onboarding.

### Webflow — **Phase 2**
- Auth: OAuth + site API token. CMS Collections API for structured content.
- Gotcha: publishing model (staged vs. live) — respect the customer's publish workflow.

### Contentful / Sanity / Shopify — **later**
- Headless CMSes (Contentful, Sanity): content goes to the CMS; rendering is the customer's app.
- Shopify (Phase 3, DTC pilot): product/collection/blog content + revenue attribution hooks.

## Analytics & search connectors (read)

### GA4 — **Phase 2**
- Auth: Google OAuth, Analytics Data API.
- Pull: sessions, conversions, channel attribution (incl. AI-referral traffic).

### Google Search Console — **Phase 2**
- Auth: Google OAuth, Search Console API.
- Pull: queries, impressions, CTR, position — baseline for lift measurement.

## CRM connectors (read — revenue attribution)

### HubSpot — **Phase 2**
- Auth: OAuth. Pull: deals/pipeline to tie AI visibility to revenue.

### Salesforce — **Phase 2**
- Auth: OAuth (connected app). Pull: opportunities/pipeline.

## AI engine access (monitoring — see specs/monitoring-engine.md)

Not "integrations" in the credential sense, but external dependencies:
- ChatGPT, Google AI Overviews, AI Mode, Gemini, Perplexity, Claude, Copilot, Grok.
- Access via official APIs where available, otherwise compliant query methods with server-side fallbacks.
- Treat each engine as replaceable; never let one exceed ~30% of delivered value.

## Model providers (reasoning brain — see docs/architecture.md)
- OpenAI (default), Anthropic, Google, OpenRouter, open models — behind the router.
- Platform-level API keys; all usage metered.

## Per-integration checklist (fill in as built)
- [ ] Auth flow implemented + token refresh
- [ ] Scopes documented
- [ ] Health check (`verify()`)
- [ ] Rate-limit handling + backoff
- [ ] Tenant-scoped credential storage
- [ ] Failure escalation path
- [ ] Notes/gotchas recorded here and in `memory.md`
