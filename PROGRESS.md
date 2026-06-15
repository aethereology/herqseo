# PROGRESS.md — QueryClear Build Tracker

> Keep this current. Check off tasks as you complete them, add newly discovered tasks,
> and reference task IDs in commits/PRs. Read this after `CLAUDE.md` and `memory.md` each session.

Legend: `[ ]` todo · `[~]` in progress · `[x]` done · `[!]` blocked

---

## Phase 0 — Foundations (do first)

- [x] **P0-1** Initialize monorepo (pnpm workspaces or Turborepo) with `apps/`, `services/`, `packages/`.
- [x] **P0-2** Set up `packages/db`: Postgres + Prisma schema, multi-tenant base tables, **row-level security** policies.
- [x] **P0-3** Set up `packages/shared`: typed contracts/constants shared across TS and consumed by Python.
- [x] **P0-4** Build the **token-metering wrapper** (all model calls route through it; enforces per-tenant budgets). See `docs/pricing-and-tiers.md`.
- [x] **P0-5** Auth + tenant model (`apps/web`): org → users → domains. Tenant context threaded everywhere.
- [x] **P0-6** `.env.example` + secrets handling; CI skeleton (lint, typecheck, test).

## Milestone 0 — Prove the operator loop (do this BEFORE Phase 1 breadth)

**Brutally narrow. One of everything. Proof metric = operator credibility, not visibility lift.**
Constraints: **one vertical** (B2B SaaS) · **one domain** · **one CMS** (WordPress) · **one autonomy mode** (Review) · **one model path** (OpenAI via the metering wrapper) · **publish to staging/draft or our own test site — NEVER a customer's live page yet.**

The loop, end to end, once: crawl one site → run visibility prompts → create opportunities → generate **one** draft → human approves → publish (staging/draft) → record token usage + full audit trail.

**Done when:** the agent reliably produces a publish-worthy draft a human approves, it publishes without breaking the target, and every model call + action is metered and audited. (Visibility/traffic lift is explicitly NOT the M0 metric — see `docs/roadmap.md`.)

- [~] **M0-1** `AgentRuntime` interface + `HermesAgentRuntime` (first impl) for one domain. See `specs/hermes-agent-layer.md`.
- [ ] **M0-2** OpenAI-only path through the token-metering wrapper.
- [ ] **M0-3** Crawl one site → visibility prompts → create opportunities.
- [ ] **M0-4** Generate ONE draft (brand-voice) → Review-mode approval gate.
- [ ] **M0-5** Publish to **staging/draft** (no live-site writes) → record audit trail + usage.
- [~] **M0-6** Thin internal UI to run the loop and approve.

## Phase 1 — Core agent loop (Month 0–3 goal: 5 customers publishing)

- [ ] **P1-1** Generalize the `AgentRuntime`/`HermesAgentRuntime` from M0 to multi-domain; expose full API to orchestration. See `specs/hermes-agent-layer.md`.
- [ ] **P1-2** Model-agnostic router (OpenAI default; pluggable providers). See `docs/architecture.md`.
- [ ] **P1-3** Domain ingestion: crawl + store a customer's site structure and content.
- [ ] **P1-4** Monitoring engine v1: audit brand visibility across 5 AI engines. See `specs/monitoring-engine.md`.
- [ ] **P1-5** Opportunity generation: produce 10 prioritized, explainable recommendations.
- [ ] **P1-6** Content engine v1: generate answer-first content with brand-voice training. See `specs/content-engine.md`.
- [ ] **P1-7** WordPress publishing connector. See `docs/integrations.md`.
- [ ] **P1-8** Autonomy slider — "Review" mode only: human approval gate before publish.
- [ ] **P1-9** Lift measurement: re-audit after 30 days, attribute change.
- [ ] **P1-10** Minimal dashboard to show audit, opportunities, drafts, approvals, and lift.

## Phase 2 — Integrations + Auto-publish (Month 3–6 goal: 20 customers, $30K MRR)

- [ ] **P2-1** Expand engine coverage to 8 (add AI Mode, Gemini, Claude, Copilot, Grok).
- [ ] **P2-2** Integrations: GA4, Google Search Console, HubSpot, Salesforce. See `docs/integrations.md`.
- [ ] **P2-3** Webflow connector (CMS #2).
- [ ] **P2-4** Technical-SEO engine v1: schema, internal links, llms.txt, meta. See `specs/technical-seo-engine.md`.
- [ ] **P2-5** Autonomy "Auto-publish" mode with brand-safety guardrails + escalation.
- [ ] **P2-6** Per-customer token budgets fully enforced + overage billing in Stripe.
- [ ] **P2-7** CRM/revenue attribution graph.
- [ ] **P2-8** Free AEO audit tool (top-of-funnel lead magnet).

## Phase 3 — Agencies + Autopilot (Month 6–12 goal: $1.5M ARR, 80+ customers)

- [ ] **P3-1** Agency Partner tier: multi-tenant white-label, per-client billing, pitch workspaces.
- [ ] **P3-2** Citation engine: prompt-gap detection + off-page outreach. See `specs/citation-engine.md`.
- [ ] **P3-3** Autonomy "Autopilot" mode + weekly review summaries.
- [ ] **P3-4** Scale tier: SSO, SOC 2 Type I, API access.
- [ ] **P3-5** Shopify integration (DTC pilot).

## Phase 4 — Defend + selective enterprise (Month 12–18 goal: $5M ARR)

- [ ] **P4-1** Per-brand model fine-tuning.
- [ ] **P4-2** On-prem / regulated-industry options.
- [ ] **P4-3** Enterprise tier hardening.

---

## Discovered tasks (add as you find them)

- [ ] Wire `services/agent-runtime` to real Hermes installation and replace the in-memory placeholder.
- [ ] Add a real DB-backed `BudgetRepository` that writes `model_usage` and updates organization usage counters.
- [ ] Replace the development Auth.js credentials provider with production auth + Prisma-backed org/user/domain lookup.
- [ ] Resolve `npm audit` moderate advisory from Next's nested `postcss@8.4.31` when a non-breaking patched Next/PostCSS path is available.
