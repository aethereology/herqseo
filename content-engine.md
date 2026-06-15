# Spec: Content Engine

**Owns:** generating answer-first content in the brand's voice and publishing it to the customer's CMS.
**Pillar 2** of the product (`docs/product-spec.md`).

## Brand-voice training
- Ingest the customer's site, docs, and prior content during onboarding.
- Produce a **brand voice profile** stored per domain (referenced by `Domain.brand_voice_profile_ref`).
- All generation conditions on this profile.

## Content types
- Answer-first topical pages, **FAQ-schema** pages, **comparison** pages, technical **glossaries**.
- Structured for AI extraction: clear questions/answers, schema markup, concise definitional passages.

## Generation flow
1. Take an approved `Opportunity` (type=content).
2. Generate draft via the router (**frontier model** for quality), conditioned on brand voice + target prompt/gap.
3. Attach structured data (FAQ/article schema) and internal-link suggestions.
4. Create a `ContentPiece` in `draft` → `pending_approval`.
5. **Review mode:** human approves in the dashboard. **Auto-publish mode:** passes brand-safety guardrails (claims, tone, grounding, word-count/topic allow-list) then publishes; escalates if out of bounds.
6. Publish via the CMS connector (`docs/integrations.md`); record `cms_post_id`, `published_at`.

## Guardrails (must exist before any auto-publish)
- No fabricated claims/stats; factual grounding required.
- Tone matches brand voice profile.
- Respect topic allow-list and length limits per autonomy config.
- Plagiarism/duplication check against existing site content.

## Cost discipline
- Generation is token-heavy → counts against the content cap and token budget per tier. All calls metered.

## Acceptance criteria (Phase 1)
- From an approved opportunity, generate a brand-voiced, schema-enriched draft, route it through Review-mode approval, publish to WordPress, and persist the full record with explainability fields.
