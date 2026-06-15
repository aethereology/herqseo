# Architecture

## Overview

QueryClear is a multi-tenant SaaS where **each customer has a dedicated autonomous agent**. The system has three planes:

1. **Control plane** (TypeScript) — the web dashboard, API, auth, billing, tenant management, and the human approval/guardrail surfaces.
2. **Agent plane** (Python) — per-customer Hermes Agent instances that do the actual work: monitor, generate, publish, fix, outreach.
3. **Data plane** (Postgres + object storage) — tenant-isolated relational data, plus blob storage for generated content and audit snapshots.

```
                ┌───────────────────────────────────────────┐
                │              CONTROL PLANE (TS)             │
   Customer ──▶ │  Next.js web  ·  API  ·  Auth  ·  Billing   │
                │  Approval gates · Autonomy slider · Tenancy │
                └───────────────┬─────────────────────────────┘
                                │ versioned contracts (packages/shared)
                ┌───────────────▼─────────────────────────────┐
                │               AGENT PLANE (Py)               │
                │  Per-customer Hermes Agent instances         │
                │  ┌────────────┐ ┌────────────┐ ┌──────────┐  │
                │  │ Monitoring │ │  Content   │ │ Technical│  │
                │  │   engine   │ │   engine   │ │   SEO    │  │
                │  └────────────┘ └────────────┘ └──────────┘  │
                │  ┌────────────┐  Model-agnostic router       │
                │  │  Citation  │  + TOKEN METERING WRAPPER     │
                │  │   engine   │  (all model calls pass here)  │
                │  └────────────┘                               │
                └───────────────┬─────────────────────────────┘
                                │
        ┌───────────────────────┼───────────────────────────┐
        ▼                       ▼                           ▼
   AI engines            Customer systems              Model providers
   (ChatGPT, AIO,        (CMS, GA4, GSC, CRM)          (OpenAI / Anthropic /
   Gemini, Perplexity…)                                 Google / open models)
```

## The per-customer agent (Hermes)

Built on **Hermes Agent** (Nous Research, open-source, MIT, Python 3.11). Why Hermes:

- **Persistent cross-session memory** — the agent retains each brand's site map, voice profile, past actions, and what moved the needle. A stateless chatbot wrapper cannot do this.
- **Self-improving skills** — it builds reusable optimization playbooks from experience.
- **Scheduled autonomous execution** — native cron-style scheduling is exactly the monitor→analyze→act loop we need.
- **40+ built-in tools** — web search, browser automation, code execution out of the box.
- **Runs anywhere cheaply** — a $5 VPS or idle-cheap serverless (Modal/Daytona), so dormant agents cost almost nothing.

**Isolation model (decide in Phase 1, see memory.md Q4):** container-per-customer gives the cleanest blast radius and is preferred once past design partners; a shared runtime with strict tenant context is acceptable for the earliest MVP. Whatever is chosen, an agent must never read another tenant's data or memory.

### Hermes sits behind an `AgentRuntime` interface (the product is not coupled to it)

Hermes is the **starting** agent framework, not a permanent dependency. The product talks to an internal **`AgentRuntime` interface**, and the Hermes wrapper is one implementation of it. This is the same philosophy we apply to the model layer — we made the *model* swappable behind a router, so we make the *agent framework* swappable behind an interface, for the identical reason: it's a young open-source project and we shouldn't bet the whole product on its memory model or scheduler before we've hit real multi-tenant load. If Hermes doesn't hold up, we swap the implementation, not the product.

```
interface AgentRuntime {
  provision(domain) -> AgentHandle
  run(handle, task) -> RunResult        // monitor / generate / fix / outreach
  getMemory(handle) / setMemory(handle, …)
  schedule(handle, cadence)
  pause(handle) / resume(handle)
  status(handle)
}
```

Feature code depends only on `AgentRuntime`. `HermesAgentRuntime` is the first concrete implementation. Keep framework-specific assumptions out of the orchestration layer. See `specs/hermes-agent-layer.md`.

## The model-agnostic brain

The reasoning engine is reached **only through an API**, never a consumer ChatGPT subscription (no programmatic API; resale violates terms; unscalable).

- **Default:** OpenAI API under commercial/business terms.
- **Routing:** a router selects the provider/model per task class — cheap models for monitoring/classification, frontier models for content generation and strategy. Pluggable across OpenAI, Anthropic, Google, OpenRouter, and open models.
- **Why this is a moat, not just plumbing:** it removes single-provider dependency on price and policy — the #1 platform risk in `docs/strategic-brief.md`.

Every call from the router passes through the **token-metering wrapper** (see below).

## Token metering (first-class subsystem)

A continuously-running agent will burn tokens and destroy margin if uncontrolled. Therefore:

- All model calls — no exceptions — go through a metering wrapper that records `(tenant, task, provider, model, input_tokens, output_tokens, cost)`.
- The wrapper enforces **per-tenant budgets** derived from plan tier (see `docs/pricing-and-tiers.md`). When a budget is exhausted, work pauses or downgrades to cheaper models, and overage is billed via Stripe.
- Target **70–80% gross margin** after API cost. Metering data feeds both billing and margin dashboards.

## The orchestration layer (our IP)

This is where engineering care concentrates. It owns:

- **Multi-tenancy** — org/user/domain model, tenant context propagation, Postgres row-level security.
- **Billing** — Stripe setup fees, subscriptions, usage-based overage.
- **Guardrails & autonomy** — the three-mode slider (Review / Auto-publish / Autopilot), brand-safety checks, approval gates, escalation.
- **Integrations** — CMS, GA4, GSC, CRM connectors (`packages/integrations`).
- **Job orchestration** — durable scheduling of the monitor→analyze→act loop (Temporal preferred).

Hermes is the commodity substrate; this layer is the product.

## Data flow: the core loop

1. **Ingest** — crawl and store the customer's site (structure, content, current schema).
2. **Monitor** — query N AI engines for brand visibility/citation/sentiment; snapshot results.
3. **Analyze** — reconcile engine signals with GA4/GSC/CRM; produce prioritized, explainable opportunities.
4. **Act** — generate content / apply technical fixes / run outreach, gated by the autonomy mode.
5. **Measure** — re-audit on schedule; attribute lift; feed learnings back into agent memory.

## Cross-cutting concerns

- **Explainability:** every recommendation traces to a specific prompt, engine, and source document, surfaced in the UI. This directly counters the "vanity dashboard" critique.
- **Observability:** structured logs + traces across the TS/Python boundary; per-tenant cost and action audit trails.
- **Security:** least-privilege credentials per integration; secrets in a vault/env; SOC 2 readiness targeted by Phase 3.

See `specs/` for per-engine detail and `docs/data-model.md` for entities.
