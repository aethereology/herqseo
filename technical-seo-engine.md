# Spec: Technical SEO/AEO Engine

**Owns:** applying on-page technical optimizations to the customer's site.
**Pillar 3** of the product (`docs/product-spec.md`). Phase 2.

## Scope of fixes
- **Schema markup** (Article, FAQ, Product, Organization, etc.).
- **Internal linking** — suggest/insert contextual links to strengthen topical clusters.
- **`llms.txt` curation** — maintain the file that guides AI crawlers.
- **AI-crawler accessibility** — robots/meta directives, ensure key content is crawlable by AI bots.
- **Meta optimization** — titles, descriptions, canonical tags.

## Application methods
1. **CMS plugin / API** (preferred) — apply changes through the connector for WordPress/Webflow/etc.
2. **JavaScript injection pixel** (where feasible) — modeled on SearchAtlas OTTO, applies changes client-side without deep CMS access. Use only with customer consent and clear rollback.

## Flow
1. Take an approved `Opportunity` (type=technical).
2. Compute the concrete change as a **diff** (store on `TechnicalFix`).
3. Gate by autonomy mode (Review approval, or Auto-publish within guardrails).
4. Apply via connector/pixel; record `applied_at` and keep the diff for rollback/audit.

## Guardrails
- Never break existing markup or canonicalization.
- Reversible changes only; keep diffs for rollback.
- Validate schema against schema.org before applying.

## Cost discipline
- Mostly deterministic transformations → use cheap models or pure code where possible; meter any model use.

## Acceptance criteria (Phase 2)
- For an approved technical opportunity, generate a validated diff, apply it via the WordPress connector under the autonomy gate, and store a reversible record.
