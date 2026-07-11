# Roadmap

Phased build plan mirroring the strategic brief. Each phase has a goal metric and maps to `PROGRESS.md` tasks.

## Phase 0 — Foundations
**Goal:** a multi-tenant skeleton with metering and tenancy in place before any agent feature.
- Monorepo, Postgres + RLS, shared contracts, **token-metering wrapper**, auth/tenant model, CI.
- Tasks: `P0-1`…`P0-6`.

## Milestone 0 — Prove the operator loop (before Phase 1 breadth)
**Goal: operator credibility, NOT visibility lift.** Run the loop once, end to end, for one domain.
- **Proof metric:** can the agent reliably produce a publish-worthy draft a human approves, publish it without breaking the target, and have every model call + action metered and audited? That's binary, fast, and fully in our control.
- **Why not lift yet:** AI answers are non-deterministic (the same prompt barely returns the same brand twice — see `specs/monitoring-engine.md`). Proving visibility/traffic lift on one domain in 30 days is statistically noisy and confounded. Lift is the *Phase 1* metric, measured across enough domains and samples to mean something.
- **Staging-first rule:** the dangerous step is writing to a customer's live site — that's where trust and liability live. M0 publishes to **staging/draft status or our own test sites only**. Live-site writes are earned in Phase 1 after the loop is proven.
- One vertical (B2B SaaS) · one domain · one CMS (WordPress) · one autonomy mode (Review) · one model path (OpenAI via metering wrapper).
- Tasks: `M0-1`…`M0-6`.

## Phase 1 — Core agent loop (Months 0–3)
**Goal:** **5 customers actively publishing; ~$50K paid setup revenue.** Now visibility lift becomes a real (multi-domain, sampled) metric.
- Generalize the M0 loop behind the `AgentRuntime` interface (Claude Agent SDK as first impl — D14) + model-agnostic router.
- Thin end-to-end slice across early customers: ingest domain → audit across 5 engines → 10 explainable opportunities → generate answer-first content → **publish to WordPress** (live writes now permitted) → measure lift across the cohort.
- Single CMS, single vertical (B2B SaaS), **Review mode only**, minimal dashboard.
- Recruit 10 design partners at Growth tier (50% off setup for case-study rights).
- Tasks: `P1-1`…`P1-10`.

## Phase 2 — Integrations + Auto-publish (Months 3–6)
**Goal:** **20 paying Growth customers; ~$30K MRR.**
- Expand to 8 engines; add GA4, GSC, HubSpot, Salesforce; Webflow connector.
- Technical-SEO engine v1; **Auto-publish mode** with brand-safety guardrails.
- Enforce per-customer token budgets + Stripe overage billing.
- Launch the free AEO audit tool (lead magnet). Begin agency conversations.
- Tasks: `P2-1`…`P2-8`.

## Phase 3 — Agencies + Autopilot (Months 6–12)
**Goal:** **$1.5M ARR; 80+ customers; 5–8 agency partners.**
- Agency Partner tier (white-label, per-client billing, pitch workspaces).
- Citation engine; **Autopilot mode** + weekly summaries.
- Scale tier (SSO, SOC 2 Type I, API); Shopify integration (DTC pilot).
- Raise Series A on published-content velocity 5–10× Searchable's claimed output.
- Tasks: `P3-1`…`P3-5`.

## Phase 4 — Defend + selective enterprise (Months 12–18)
**Goal:** **$5M ARR; NRR >120%; seven-figure pipeline from displaced agency retainers.**
- Per-brand model fine-tuning; on-prem/regulated options; enterprise hardening.
- Tasks: `P4-1`…`P4-3`.

## Guiding principles across phases
- **Vertical slices first** — prove the loop before breadth.
- **Tenancy + metering are never deferred.**
- **Guardrails precede autonomy** at every step.
- Re-evaluate the three pivot plans in `docs/strategic-brief.md` ("What changes if I'm wrong") at each phase boundary.
