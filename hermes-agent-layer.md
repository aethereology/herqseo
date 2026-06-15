# Spec: Agent Runtime Layer (Hermes is the first implementation)

**Owns:** the per-customer autonomous agent — provisioning, memory, skills, scheduling, and the model-agnostic brain.
**Lives in:** `services/agent-runtime` (Python 3.11).

## Design rule: program to `AgentRuntime`, not to Hermes
The rest of the product depends on an internal **`AgentRuntime` interface** (see `docs/architecture.md`), never on Hermes directly. `HermesAgentRuntime` is the first concrete implementation. Hermes is our starting choice — strong fit, but a young framework — so all framework-specific behavior stays behind the interface. If we outgrow or replace it, we swap the implementation, not the product.

```
AgentRuntime:  provision · run · get/setMemory · schedule · pause · resume · status
HermesAgentRuntime implements AgentRuntime
```

## Responsibilities
- Provision and manage **one agent instance per customer domain**.
- Maintain each agent's **persistent memory** (brand profile, site map, voice, action history, what worked).
- Run **scheduled autonomous work** (monitor→analyze→act) on a per-customer cadence.
- Expose the `AgentRuntime` API to the control plane (provision, run, status, fetch results, pause/resume).
- Route all reasoning through the **model-agnostic router** + **token-metering wrapper**.

## Hermes setup
- Install per Hermes docs (one-line installer; `uv`, Python 3.11).
- Configure model provider to QueryClear's router endpoint, **not** a consumer ChatGPT login.
- Enable the tools we need: web search, browser automation, code execution; register custom **skills** for our four engines.

## Per-agent memory
- Each agent's memory is isolated and referenced by `AgentInstance.memory_store_ref` (see `docs/data-model.md`).
- Store: brand voice profile, site structure, prior opportunities/outcomes, engine-specific learnings.
- Never co-mingle memory across tenants.

## Model-agnostic router (lives here)
- Selects provider/model per **task class**:
  - monitoring/classification/extraction → cheap, fast models
  - content generation, strategy, reasoning → frontier models
- Providers: OpenAI (default), Anthropic, Google, OpenRouter, open models.
- Pluggable + config-driven; a provider outage or price change is a config swap, not a rewrite.

## Token-metering wrapper (lives here, mandatory)
- Every model call passes through it. Records `ModelUsage` (see data model) and enforces `token_budget_monthly`.
- Implements soft-cap downgrade and hard-cap pause per `docs/pricing-and-tiers.md`.
- **No feature code may call a provider SDK directly.**

## Isolation
- Container-per-customer preferred at scale; shared runtime with strict tenant context acceptable for earliest MVP (see `memory.md` Q4). Decide and record.

## Internal API (sketch)
```
POST /agents                  # provision agent for a domain
POST /agents/{id}/run         # trigger a run (or scheduled)
GET  /agents/{id}/status
GET  /agents/{id}/results     # opportunities, drafts, fixes pending
POST /agents/{id}/pause | /resume
```
Contracts versioned in `packages/shared`.

## Acceptance criteria (Phase 1)
- Provision an agent for one domain, run the core loop on a schedule, produce opportunities and drafts, respect Review-mode gating, and record token usage for every call.
