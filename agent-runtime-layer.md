# Spec: Agent Runtime Layer (Claude Agent SDK is the first implementation)

**Owns:** the per-customer autonomous agent — provisioning, memory, scheduling, and the agent session that decides and executes operator runs.
**Lives in:** `services/agent-runtime` (Python 3.11).

> History: Hermes Agent (Nous Research) was the originally planned substrate but was never installed — the "HermesAgentRuntime" was always an in-memory stub. Dropped for the **Claude Agent SDK** in Session 32 (decision **D14** in `memory.md`).

## Design rule: program to `AgentRuntime`, not to the SDK

The rest of the product depends on an internal **`AgentRuntime` interface** (`runtime.py`), never on the Claude Agent SDK directly. `ClaudeAgentRuntime` (`claude_runtime.py`) is the first concrete implementation. All framework-specific behavior stays behind the interface; if we outgrow or replace the SDK, we swap the implementation, not the product.

```
AgentRuntime:  provision · get · list · run · get/setMemory · schedule · results · pause · resume · status
ClaudeAgentRuntime implements AgentRuntime   (claude_runtime.py)
```

## What a run is (v1)

`ClaudeAgentRuntime.run()` = one operator run = one Claude Agent SDK session with exactly **three in-process MCP tools**, all closures over the framework-free `LoopService`:

- `run_operator_loop` — runs crawl → visibility monitoring → one content draft. **Pinned to the task payload's domain/brand**: the agent decides *whether* to run, never *which* domain to hit.
- `get_recent_results` — prior runs, action history, and learnings, so the agent reasons over history.
- `write_run_report` — a summary + learnings; learnings persist into agent memory.

There is **no publish tool and no built-in tools** (`allowed_tools` whitelists only the three). Publishing stays behind the human review endpoints; `assert_approved_for_publish` / `ApprovalRequired` is the backstop. The deterministic endpoints (`/runs`, `/audit`, review, publish, WordPress) call `LoopService` directly and never go through the agent.

## Metering (mandatory, unchanged rule)

The whole SDK session is metered as **one** `TokenMeter.run_metered` call (`task_class="agent_run"`, provider `anthropic`):

- **Reserve before spend:** the run-level reservation (`QUERYCLEAR_AGENT_RESERVE_*_TOKENS`, default 150k in / 50k out) is checked against the org budget before the session starts; an unaffordable run raises `BudgetExceeded` → HTTP **402** with zero spend.
- **Settle from SDK-reported usage:** the `ResultMessage` usage + `total_cost_usd` become the `UsageRecord`.
- Model calls the loop makes *inside* tools meter themselves through `run_model()` as always (nested reservations are conservative but correct).
- `max_turns` (default 12) bounds the session. Live interrupt-on-overrun is a later upgrade (`ClaudeSDKClient.interrupt()`).
- **No feature code may call a provider SDK directly.**

## Model routing coexistence

The SDK session is Anthropic-native (`QUERYCLEAR_AGENT_MODEL`, default `claude-sonnet-4-6`) — it is the orchestration brain. Task-level model calls inside `LoopService` (classification, monitoring, content generation) still route through `providers.py`'s `ModelRoutingPolicy`, so bulk work stays on whichever provider the routes say. The `AgentRuntime` interface remains the swap seam for the substrate itself.

## Setup

```
pip install -e ".[agent]"      # claude-agent-sdk (ships a bundled CLI — no separate Node install)
export ANTHROPIC_API_KEY=...   # without it, agent runs use the offline demo session
```

Config (see `.env.example`): `QUERYCLEAR_AGENT_MODEL`, `QUERYCLEAR_AGENT_MAX_TURNS`, `QUERYCLEAR_AGENT_RESERVE_INPUT_TOKENS`, `QUERYCLEAR_AGENT_RESERVE_OUTPUT_TOKENS`.

The SDK is deliberately **not** in `requirements.txt` (the Vercel audit-function manifest) — agent runs happen on the uvicorn host (`serve.py`), not in the stateless audit function.

## Testability

`ClaudeAgentRuntime(session_runner=...)` is the injection seam (same philosophy as `client=` on the providers). Tests and demo mode inject a fake runner that replays canned tool calls against the real tool closures — CI stays offline and never needs the SDK installed. `demo_session_runner` scripts the canonical check-history → run-loop → write-report session.

## Per-agent memory

- Isolated per agent, referenced by `AgentHandle.memory_store_ref`; in-memory today, DB-backed later.
- Stores: brand profile, action history (with run reports), learnings from `write_run_report`.
- Never co-mingle memory across tenants.

## Internal API (implemented in `app.py`)

```
POST /agents                  # provision agent for a domain
GET  /agents                  # list (filter by org/domain)
POST /agents/{id}/run         # trigger a run — 402 if over budget
GET  /agents/{id}/status
GET  /agents/{id}/results
GET|PUT /agents/{id}/memory
POST /agents/{id}/schedule    # stored; scheduler execution is a later phase
POST /agents/{id}/pause | /resume
```

## Deferred ("later")

Scheduled autonomous runs (cron/Modal hitting `/agents/{id}/run`), live budget interrupt mid-run, DB-backed agent registry/memory, SDK session resume, additional tools (technical fixes, citation outreach), agent-runs dashboard.

## Acceptance criteria (v1 — met)

- Provision an agent per org/domain; trigger a run that produces real opportunities and a draft via the loop; Review-mode gating holds (the agent cannot publish); the run is rejected up front when the org budget can't cover the reservation; every run and every inner model call is metered.
