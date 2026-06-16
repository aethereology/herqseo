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
- [x] **M0-2** OpenAI-only path through the token-metering wrapper. `OpenAIProvider` (lazy SDK import) + data-driven `OPENAI_PRICING` + `run_model()` glue; SDK call never bypasses the meter. Tests cover cost math and over-budget gating.
- [x] **M0-3** Crawl one site → visibility prompts → create opportunities. `crawl.py` (bounded seed-path fetch, stdlib HTML parse, lazy httpx) → `monitoring.py` (`derive_prompts` → metered `run_visibility_checks` with repeated sampling → `generate_opportunities`), orchestrated by `run_monitoring()`. Every sample metered; opportunities are explainable (rationale + prompt trace). Offline-tested with fake fetcher/provider.
- [x] **M0-4** Generate ONE draft (brand-voice) → Review-mode approval gate. `content.py`: `BrandVoice`, `generate_content_draft` (frontier model, answer-first system prompt, metered, rejects non-content opps) → `ContentPiece` (`pending_approval`); `review_content` records approve/reject + reviewer; `assert_approved_for_publish` blocks any publish unless `approved` in Review mode (auto modes disabled in M0). Schema/internal-links/guardrails deferred to P1-6.
- [x] **M0-5** Publish to **staging/draft** (no live-site writes) → record audit trail + usage. `publishing.py`: `CmsPublisher` interface + `WordPressPublisher` (draft-only; `StagingOnlyError` blocks live writes, lazy httpx), `publish_content` runs the approval gate then publishes and appends an `AuditEvent` linking the publish to the approver + the metered `usage_record_id`. End-to-end loop proven in `test_loop_e2e.py` (crawl→monitor→opportunity→draft→approve→publish-draft, metered + audited).
- [x] **M0-7** Persist operator state across restart. Repository seam (`repositories.py`: `DraftRepository`/`OpportunityRepository`/`AuditEventRepository` Protocols + `InMemory*` defaults; `db.py`: tenant-scoped `Sql*` impls) replaces `LoopService`'s in-memory `_drafts`/`audit_log`. Migration `0002_runtime_persistence` extends `content_pieces` (inline body + review/cost/model cols; `body_ref` nullable) and adds an `audit_events` table with RLS. Runtime IDs → `uuid4` to match uuid PKs/FKs; draft lifecycle threads `org_id` end to end (tenant-scoped). `serve.py` wires the Sql repos when `DATABASE_URL` is set. **Validated against real Postgres (Session 20):** migrations applied, run→review→publish→restart persists, RLS isolates tenants, budget metered — fixed 3 Postgres-only type bugs SQLite couldn't catch (uuid/enum/timestamptz `with_variant` types; +missing `ContentStatus` `approved`/`rejected` enum values). Remaining: a CI Postgres service so those mismatches can't regress.
- [x] **M0-6** Thin internal UI to run the loop and approve. `LoopService` + FastAPI adapter (`app.py`) + runnable `serve.py` (`build_app` factory, offline demo mode when no keys). `apps/web` operator console (`OperatorConsole.tsx`) drives run→review→publish via authenticated Next proxy routes (`/api/loop/run|review|publish`) → runtime; replaces the old hardcoded review queue. Verified end-to-end via curl against the demo service: gate returns 409 before approval, publishes as `draft` (staging only), audit records a usage-linked publish event. Not yet exercised with a real OpenAI key / live WordPress, and not browser-tested.

## Phase 1 — Core agent loop (Month 0–3 goal: 5 customers publishing)

- [ ] **P1-1** Generalize the `AgentRuntime`/`HermesAgentRuntime` from M0 to multi-domain; expose full API to orchestration. See `specs/hermes-agent-layer.md`.
- [ ] **P1-2** Model-agnostic router (OpenAI default; pluggable providers). See `docs/architecture.md`.
- [ ] **P1-3** Domain ingestion: crawl + store a customer's site structure and content.
- [ ] **P1-4** Monitoring engine v1: audit brand visibility across 5 AI engines. See `specs/monitoring-engine.md`.
- [ ] **P1-5** Opportunity generation: produce 10 prioritized, explainable recommendations.
- [~] **P1-6** Content engine v1: generate answer-first content with brand-voice training. See `specs/content-engine.md`. *Per-domain brand voice now flows end-to-end (Session 18): `DomainSummary.brandVoice` → web proxy → runtime `brand_voice` → `LoopService._voice_for()` → content system prompt. Fixed a latent bug where drafts ignored the requested brand and used the default. Still to do: **training** the voice from the customer's own site/docs (currently a guideline string).*
- [ ] **P1-7** WordPress publishing connector. See `docs/integrations.md`.
- [ ] **P1-8** Autonomy slider — "Review" mode only: human approval gate before publish.
- [ ] **P1-9** Lift measurement: re-audit after 30 days, attribute change.
- [ ] **P1-10** Minimal dashboard to show audit, opportunities, drafts, approvals, and lift.

## Phase 2 — Integrations + Auto-publish (Month 3–6 goal: 20 customers, $30K MRR)

- [ ] **P2-1** Expand engine coverage to 8 (add AI Mode, Gemini, Claude, Copilot, Grok).
- [ ] **P2-2** Integrations: GA4, Google Search Console, HubSpot, Salesforce. See `docs/integrations.md`.
- [ ] **P2-3** Webflow connector (CMS #2).
- [~] **P2-4** Technical-SEO engine v1: schema, internal links, llms.txt, meta. See `specs/technical-seo-engine.md`. *Detection slice landed in the audit (Session 18): `technical.py` flags missing meta-description, missing structured data (JSON-LD/microdata), missing robots.txt, missing llms.txt; crawler captures meta + schema presence. Still to do: internal-link analysis, and the **fixing** side (generating schema/meta/llms.txt), which is the actual engine.*
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
- [~] Add a real DB-backed `BudgetRepository` that writes `model_usage` and updates organization usage counters. **Done:** `db.py` `SqlBudgetRepository` (SQLAlchemy Core; writes `model_usage` + increments `organizations.token_used_current_period` atomically; sets `app.current_org` for RLS on Postgres; tested offline on SQLite). `serve.py` uses it when `DATABASE_URL` is set. **Remaining:** validate against a real Postgres + apply the migration; persist `ContentPiece`/`Opportunity`/`AuditEvent` too.
- [ ] Replace the development Auth.js credentials provider with production auth + Prisma-backed org/user/domain lookup.
- [ ] Resolve `npm audit` moderate advisory from Next's nested `postcss@8.4.31` when a non-breaking patched Next/PostCSS path is available.
