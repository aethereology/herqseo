# Product Spec

## What QueryClear does

A true operator that closes the loop across four pillars, end-to-end, with humans-in-the-loop only at approval gates.

### Pillar 1 — Visibility monitoring & analytics
- Track brand visibility, citation share, and sentiment across **8+ AI engines**: ChatGPT, Google AI Overviews, Google AI Mode, Gemini, Perplexity, Claude, Copilot, Grok (add Amazon Rufus and Meta AI by month 12).
- Reconcile AI-visibility signals with **GA4 + Google Search Console + CRM** to attribute visibility to pipeline and revenue.
- Output: explainable visibility scores, share-of-voice vs. competitors, and prioritized gaps — each traceable to the exact prompt, engine, and source.

### Pillar 2 — Content generation & publishing
- Generate **answer-first structured content**: FAQ-schema pages, comparison pages, technical glossaries, and topical answer pages.
- **Brand-voice training** from ingested customer materials (site, docs, prior content).
- **Publish directly into the customer's CMS**: WordPress and Webflow first; then Contentful, Sanity, Shopify.

### Pillar 3 — Technical SEO/AEO execution
- Apply on-page fixes via CMS plugin or (where feasible) a JavaScript injection pixel modeled on SearchAtlas OTTO.
- Scope: schema markup, internal linking, `llms.txt` curation, AI-crawler accessibility, meta optimization.

### Pillar 4 — Off-page citation campaigns
- Prompt-gap detection (where the brand should appear in AI answers but doesn't).
- Surface Reddit / YouTube / Wikipedia citation opportunities.
- Automated outreach for citation placement.

## The autonomy slider (key differentiator)

A configurable control with three modes:

| Mode | Behavior | Typical use |
|---|---|---|
| **Review** (default) | Agent proposes; human approves every action before it happens. | New customers, first 60–90 days. |
| **Auto-publish** | Agent executes within pre-approved guardrails (schema, internal links, content <1,500 words on approved topics); escalates anything outside the box. | Customers who've built trust. |
| **Autopilot** | Full execution with weekly review summaries. | Mature, high-trust accounts. |

Most mid-market B2B SaaS buyers start in Review and graduate to Auto-publish. **This is the explicit contrast with Searchable's "export tasks to Linear for humans" model and Profound's pure monitoring.**

## Explainability requirement

Every recommendation and action must surface its reasoning: which prompt, which engine, which source document, what changed, and the confidence interval. This is a hard product requirement — it's the antidote to the category-wide "vanity dashboard" complaint.

## Integration requirements (day-one bar)

Native integration with **GA4, GSC, HubSpot, Salesforce, Shopify, and at least three CMSes**. The attribution graph should be the deepest in the mid-market — AthenaHQ wins on Shopify revenue attribution; we should win broadly.

## What we deliberately are NOT (for now)

- Not an enterprise-first platform (Bluefish/Profound own that; long sales cycles burn cash).
- Not a sub-$100/mo SMB tool (unit economics break).
- Not a DTC-launch product (Shopify is a Phase 3 expansion, not the beachhead).
- Not a done-for-you human services agency (we replace that model, not become it).

See `docs/strategic-brief.md` for the full rationale and `specs/` for how each pillar is built.
