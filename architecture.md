# Architecture

## Overview

QueryClear is a multi-tenant SaaS where **each customer has a dedicated autonomous agent**. The system has three planes:

1. **Control plane** (TypeScript) — the web dashboard, API, auth, billing, tenant management, and the human approval/guardrail surfaces.
2. **Agent plane** (Python) — per-customer agent instances (Claude Agent SDK behind `AgentRuntime`) that do the actual work: monitor, generate, publish, fix, outreach.
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
                │  Per-customer agent instances (Claude SDK)   │
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

## The per-customer agent (Claude Agent SDK)

Built on the **Claude Agent SDK** (Anthropic, Python, `claude-agent-sdk`). Chosen in Session 32 (decision **D14** in `memory.md`) after dropping the original Hermes plan — Hermes was never installed, so the swap cost nothing. Why the SDK:

- **A real agentic loop today** — sessions with tool use, `max_turns` bounds, and per-session usage reporting that plugs straight into our token metering.
- **In-process custom tools** — the agent's tool surface is exactly the three `LoopService` wrappers we define (no publish tool), which is the guardrail model we want.
- **Ships a bundled CLI** — `pip install` is the whole footprint; no separate Node install on the runtime host.
- **Persistent memory per brand** stays in our own `AgentRuntime` store (in-memory today, DB later) — deliberately not coupled to SDK session files.

**Isolation model (decide in Phase 1, see memory.md Q4):** container-per-customer gives the cleanest blast radius and is preferred once past design partners; a shared runtime with strict tenant context is acceptable for the earliest MVP. Whatever is chosen, an agent must never read another tenant's data or memory.

### The SDK sits behind an `AgentRuntime` interface (the product is not coupled to it)

The Claude Agent SDK is the **first** agent substrate, not a permanent dependency. The product talks to an internal **`AgentRuntime` interface**, and `ClaudeAgentRuntime` is one implementation of it. This is the same philosophy we apply to the model layer — we made the *model* swappable behind a router, so we make the *agent framework* swappable behind an interface. If the SDK doesn't hold up, we swap the implementation, not the product.

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

Feature code depends only on `AgentRuntime`. `ClaudeAgentRuntime` (`claude_runtime.py`) is the first concrete implementation; the agent session is Anthropic-native by choice, while task-level model calls inside the loop still route through the model router below. Keep framework-specific assumptions out of the orchestration layer. See `agent-runtime-layer.md`.

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

The agent SDK is the commodity substrate; this layer is the product.

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
