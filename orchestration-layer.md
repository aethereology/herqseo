# Spec: Orchestration Layer (the IP)

**Owns:** multi-tenancy, billing, autonomy/guardrails, integration coordination, and durable job scheduling.
**Lives in:** `apps/api` + `apps/web` (TypeScript), with `packages/db` and `packages/integrations`.

This is the defensible product. Invest the most engineering care here.

## 1. Multi-tenancy
- Org → users → domains hierarchy (`docs/data-model.md`).
- **Row-level security** on every tenant table; app code sets `app.current_org` per request/job and also scopes queries explicitly.
- A test must prove cross-tenant access fails. This ships in Phase 0, not later.

## 2. Billing (Stripe)
- One-time **setup fee** on activation.
- Tiered **subscription** per `docs/pricing-and-tiers.md`.
- **Usage-based overage** fed by `ModelUsage` and the publish pipeline.
- Tier config is data-driven; changing prices/limits never requires a redeploy.

## 3. Autonomy & guardrails
- Three modes — Review / Auto-publish / Autopilot (`docs/product-spec.md`).
- **Guardrails before autonomy:** brand-safety checks (prohibited claims, tone, factual grounding), scope limits (word count, topic allow-list), and an **escalation path** for anything out of bounds.
- Every approve/reject is recorded as an `ApprovalEvent` (audit trail).
- Auto-publish/Autopilot code paths must not merge until the guardrail checks and escalation exist.

## 4. Integration coordination
- Reads (GA4/GSC/CRM) feed the analyze step; writes (CMS publish, technical fixes) are gated by autonomy mode.
- All connectors implement the common interface in `packages/integrations` (`docs/integrations.md`).

## 5. Durable job orchestration
- The monitor→analyze→act loop runs as durable workflows (Temporal preferred): retries, backoff, long-running steps, per-tenant schedules.
- Each customer has a cadence (e.g., daily monitor, weekly content batch) bounded by their token budget.

## 6. Explainability surface
- The dashboard renders, for every opportunity/action: prompt, engine, source doc, diff, confidence. Backed by the `Opportunity`/`ContentPiece`/`TechnicalFix` fields.

## Acceptance criteria (Phase 1)
- A design-partner org can be created, a domain added, an agent provisioned, opportunities and drafts reviewed/approved in the UI, content published to WordPress, and the action fully audited — all tenant-isolated, all model usage metered and attributable to billing.
