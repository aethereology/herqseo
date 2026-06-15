# Tech Stack

These are committed defaults. Deviations are allowed but must be recorded in `memory.md` with rationale.

## Languages & runtimes
- **TypeScript / Node 20+** — control plane (web, API, integrations contracts).
- **Python 3.11** — agent runtime (Hermes is Python-native).

Polyglot is deliberate: Hermes and the AI/agent tooling live best in Python; the SaaS app, billing, and multi-tenant API are faster and safer in typed TypeScript. The boundary is an explicit, versioned contract in `packages/shared`.

## Frontend
- **Next.js (App Router)** + **TypeScript**
- **Tailwind CSS** + **shadcn/ui** for components
- Server components for data-heavy dashboard views; keep the approval/guardrail UX snappy.

## Backend / API
- TypeScript. Either Next.js route handlers (MVP) or a standalone Node service as it grows.
- Validate all I/O with a schema library (e.g. Zod); share schemas via `packages/shared`.

## Agent runtime
- **Hermes Agent** (Nous Research) wrapped in a thin service that the control plane calls over the versioned contract.
- Python deps managed with **uv**.
- The model-agnostic **router** + **token-metering wrapper** live here; no feature code calls a provider SDK directly.

## Data
- **PostgreSQL 15+** as the system of record.
- **Multi-tenancy via row-level security (RLS)** — the enforcement backstop. App code still scopes every query by tenant.
- **Prisma** on the TS side (schema + migrations in `packages/db`). Python side uses async SQLAlchemy or an asyncpg layer reading the same DB; RLS keeps both honest.
- **Object storage** (S3-compatible) for generated content, audit snapshots, and crawl artifacts.

## Jobs & scheduling
- **Temporal** preferred for the durable monitor→analyze→act loop (retries, long-running workflows, visibility). **BullMQ** acceptable for the earliest MVP if Temporal setup slows the first slice.
- Per-customer schedules drive recurring audits and publishing cadence.

## Auth
- **Auth.js** or **Clerk** — org → users → roles. Must integrate cleanly with the tenant model.

## Billing
- **Stripe** — three mechanics:
  1. one-time **setup fees**,
  2. tiered **subscriptions**,
  3. **usage-based overage** (metered tokens / published pieces / extra engines).
- Usage records come from the token-metering wrapper and the publish pipeline.

## Model providers
- **OpenAI API** default; **Anthropic**, **Google**, **OpenRouter**, and open models behind the router.
- Provider keys are platform-level secrets, not per-customer consumer logins.

## Infra & deploy
- Containerized; **agents isolated per customer** (container-per-tenant preferred at scale).
- Serverless-friendly (Modal / Daytona) so idle agents cost ~nothing.
- IaC (Terraform or Pulumi) once past the first slice.

## Observability
- Structured logging + distributed tracing across the TS/Python boundary.
- Per-tenant cost dashboards (fed by metering) and action audit trails.

## Testing
- TS: Vitest/Jest + Playwright for the approval-gate flows.
- Python: pytest for engines and the router/metering wrapper.
- Mandatory coverage on billing, token metering, and tenant isolation.

## Recommended build order
Follow `PROGRESS.md` Phase 0 → Phase 1. Stand up DB + tenancy + metering **before** any agent feature work.
