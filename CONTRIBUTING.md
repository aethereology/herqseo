# Contributing & Development Conventions

## Setup (target — fill in as the monorepo is built)

```bash
# Prereqs: Node 20+, pnpm, Python 3.11, Postgres 15+, Docker
pnpm install
cp .env.example .env        # fill in secrets
pnpm db:migrate             # apply Prisma migrations + RLS policies
pnpm dev                    # run web + api
# Agent runtime:
cd services/agent-runtime && uv sync && uv run dev
```

Keep this section accurate. If a command changes, update it here and note it in `memory.md`.

## Working agreements

- **Read before you write.** Each session: `CLAUDE.md` → `memory.md` → `PROGRESS.md`.
- **One task per PR**, referencing a `PROGRESS.md` task ID (e.g. `P1-7`).
- **Conventional Commits:** `feat:`, `fix:`, `chore:`, `docs:`, `refactor:`, `test:`.
- **Vertical slices over horizontal layers** — ship thin end-to-end paths first.

## Non-negotiables (these protect the business)

1. **Tenant isolation everywhere.** Every query is tenant-scoped. Postgres row-level security is the enforcement backstop, not an excuse to skip scoping in app code. Add a test proving cross-tenant access fails.
2. **All model calls go through the token-metering wrapper.** No direct provider SDK calls in feature code. Budgets are enforced, usage is recorded for billing.
3. **Guardrails before autonomy.** No auto-publish path merges without brand-safety checks and an escalation route.
4. **Secrets via env only.** Update `.env.example` whenever you add a required variable.
5. **Document integrations as you build them** in `docs/integrations.md`.

## Testing priorities

Test the money-and-trust paths first: billing/Stripe, token metering, tenant isolation, and the publish approval gate. Everything else is recoverable; these are not.

## Cross-language boundary (TS ↔ Python)

The web/API layer is TypeScript; the agent runtime is Python. Communicate over an explicit, versioned contract defined in `packages/shared`. Don't pass loosely-typed blobs across the boundary.

## Definition of done

- Code typechecks, lints, and tests pass.
- Tenant scoping verified.
- `memory.md` and `PROGRESS.md` updated.
- Repo left runnable (or breakage clearly noted in `memory.md`).
