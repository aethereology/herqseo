# memory.md — QueryClear Working Memory

> **UPDATE THIS MEMORY AFTER EACH SESSION.**
> This file is how Claude Code stays intelligent across sessions. Before you stop working,
> append a new dated entry to the Session Log below and refresh the "Current State" section.
> At the start of each session, read this file in full before touching code.

---

## How to maintain this file

- **Current State** (below) is a living snapshot — overwrite it so it always reflects reality *now*.
- **Session Log** is append-only — add a new entry each session; never delete history.
- **Decisions** is append-only — record every architectural or product decision and *why*, so future sessions don't relitigate or accidentally reverse them.
- **Open Questions / Risks** — keep current; remove items once resolved (and note the resolution in Decisions).
- Keep entries concrete: file paths, command names, env vars, function names. Future-you has no other memory.

---

## Current State (overwrite each session)

**Phase:** Phase 0 scaffold started.
**Last updated:** Session 4 (Auth.js tenant context).
**What runs today:** `npm run ci`, `npm run build`, and `npm run test:py` pass. The web app has Auth.js credentials sign-in, tenant-scoped sessions, a protected dashboard, and `/api/tenant/context`.
**Next concrete step:** Continue `M0-1` by replacing the in-memory `HermesAgentRuntime` placeholder with a real Hermes-backed implementation, then wire `M0-2` OpenAI calls through the token meter.
**Known broken / incomplete:** Auth is development credentials only; no production OAuth/SSO, Prisma-backed user lookup, live DB server, DB-backed budget repository, Hermes install, OpenAI provider call, crawler, WordPress connector, or approval action yet. `npm audit` reports 2 moderate advisories from Next's nested `postcss@8.4.31`; npm's suggested fix is breaking. In-app Browser was unavailable in Session 2 (`agent.browsers.list()` returned `[]`), so visual verification used build + HTTP checks only. GitHub remote is `https://github.com/aethereology/herqseo.git`; local `main` has the latest auth commit, but pushing from Codex failed because the non-interactive shell could not prompt for GitHub credentials.

---

## Session Log (append-only)

### Session 1 — Incorporated external review feedback
- An external review (ChatGPT) flagged: (a) scope sprawl, (b) couple-to-Hermes risk, (c) proof-metric choice. Assessed as largely correct on execution discipline.
- Changes folded into docs: added the **`AgentRuntime` interface** (Hermes = first impl) in `architecture.md`, `specs/hermes-agent-layer.md`, and `CLAUDE.md`; added **Milestone 0** (brutally narrowed first build) to `PROGRESS.md` and `roadmap.md`; reframed the M0 **proof metric to operator credibility** (not visibility lift) and added the **staging-first / no-live-writes rule**.
- Logged as decisions D7, D8, D9 below.
- Refinement beyond the review: M0 proof metric is explicitly operator credibility, not lift (lift too noisy on one domain); and the staging-first rule was added because live-site writes are where trust/liability concentrate.
- **Next session should:** scaffold the monorepo (Phase 0), then start `M0-1` (AgentRuntime interface + HermesAgentRuntime for one domain).

### Session 2 — Initial runnable monorepo scaffold — 2026-06-15
- What I did: created npm workspace scaffold with `apps/web`, `apps/api`, `packages/shared`, `packages/db`, `packages/integrations`, and `services/agent-runtime`; installed dependencies and generated `package-lock.json`.
- Added `apps/web` Next.js App Router dashboard shell for the one-domain Review-mode operator loop; added Tailwind and ESLint config.
- Added `packages/shared` TypeScript contracts/constants for plan tiers, autonomy modes, AI engines, tenant context, agent requests/results, and model usage records.
- Added `packages/db/prisma/schema.prisma` plus `packages/db/migrations/0001_initial_tenancy/migration.sql` with base tenant tables and RLS policies using `app.current_org`.
- Added `services/agent-runtime` Python `AgentRuntime` interface, in-memory `HermesAgentRuntime` placeholder, token-metering wrapper, and 5 unittest tests for metering/runtime behavior.
- Added `.env.example`, `.github/workflows/ci.yml`, root lint/typecheck/test/build scripts, and README quick-start commands.
- Verification: `npm run lint`, `npm run typecheck`, `npm run ci`, `npm run build`, and `Invoke-WebRequest http://127.0.0.1:3000/` all passed. Dev server startup can take more than 5 seconds; a 20-second wait returned HTTP 200.
- Key decisions made: use npm workspaces for the initial scaffold because local `pnpm --version` failed with an EPERM sandbox error. Recorded as D10.
- What's in progress / half-done: `M0-1` has the interface and placeholder runtime only; `M0-6` has a static UI shell only; no actual loop execution exists yet.
- What the next session should do first: implement `P0-5` tenant/auth context, then make `TokenMeter` persist to Postgres via `model_usage` and wire a real OpenAI-only model path through the meter.
- Gotchas / things that bit me: `npm run dev -- --hostname/--port` is parsed incorrectly on this Windows/npm setup; use `npx next dev -H 127.0.0.1 -p 3000` from `apps/web`. In-app Browser was unavailable, so no screenshot verification was possible.

### Session 3 — GitHub remote confirmed — 2026-06-15
- What I did: confirmed `origin` is `https://github.com/aethereology/herqseo.git`, fetched `origin`, and checked local/remote branch state.
- Repo state: `main` is clean but ahead of `origin/main` by one local commit: `c667120 ci: add CI workflow`, which adds `.github/workflows/ci.yml`.
- Push attempt: `git push origin main` was rejected by GitHub because the configured Personal Access Token cannot create/update workflow files without the `workflow` scope.
- Next session should either use a GitHub credential with `workflow` scope and push `main`, or decide to move/remove the workflow commit before pushing.

### Session 4 — Auth.js tenant context — 2026-06-15
- What I did: completed `P0-5` with Auth.js v5 beta in `apps/web`, using a development credentials provider that emits a tenant-scoped JWT session from `QUERYCLEAR_DEV_*` env values.
- Added shared tenant model types in `packages/shared/src/index.ts`: `OrganizationSummary`, `DomainSummary`, `UserSummary`, and `AuthenticatedTenant`.
- Added `apps/web/auth.ts`, Auth.js route handlers, session/JWT type augmentation, sign-in/sign-out server actions, a `/sign-in` page, protected dashboard tenant rendering, and `/api/tenant/context`.
- Verification: `npm run typecheck`, `npm run lint`, `npm run ci`, and `npm run build` pass. Production-mode HTTP checks with `AUTH_SECRET` and `AUTH_TRUST_HOST=true` verified unauthenticated session returns `null`, `/api/tenant/context` returns 401 without a session, `/sign-in` returns 200, `/` redirects to `/sign-in`, credentials callback returns 302, and authenticated `/api/tenant/context` returns the expected tenant payload.
- Key decisions made: use Auth.js credentials only as a local/M0 bridge until a real Prisma-backed org/user/domain lookup and production provider are added. Do not treat it as production auth.
- What the next session should do first: start `M0-1` real Hermes integration or `M0-2` OpenAI-only model path through the token meter.
- Gotchas / things that bit me: Auth.js requires `AUTH_SECRET` in production mode and rejects local hosts unless `AUTH_TRUST_HOST=true`; both are now documented in `.env.example`. `git push origin main` failed from Codex because the shell could not open an interactive GitHub credential prompt.

### Session 0 — Project scaffold created
- Created the documentation and spec scaffold: `CLAUDE.md`, `memory.md`, `PROGRESS.md`, `README.md`, `CONTRIBUTING.md`, full `docs/` and `specs/` trees.
- No code yet. The strategy is locked (see `docs/strategic-brief.md`); engineering decisions captured in `docs/tech-stack.md` and `docs/architecture.md`.
- **Next session should:** scaffold the monorepo and stand up the thinnest end-to-end slice (ingest one domain → audit → generate → publish to WordPress → measure).

<!--
TEMPLATE FOR NEW ENTRIES — copy this block:

### Session N — <short title> — <date>
- What I did:
- Key decisions made (also add to Decisions section if architectural):
- What's in progress / half-done:
- What the next session should do first:
- Gotchas / things that bit me:
-->

---

## Decisions (append-only — the "why" behind the build)

- **D1 — Per-customer Hermes agent.** Each customer gets a dedicated Hermes Agent instance (Nous Research, Python, MIT). Chosen for persistent memory, self-improving skills, and scheduled autonomy. Rationale in `docs/architecture.md`.
- **D2 — Model-agnostic brain via API; never a consumer ChatGPT subscription.** Consumer ChatGPT has no programmatic API and resale violates terms. Default to OpenAI API, route across providers per task. This also mitigates platform-dependency risk.
- **D3 — Orchestration layer is the IP.** Multi-tenancy, billing, guardrails, autonomy slider, and integrations are proprietary and get the most engineering care; Hermes is the commodity substrate underneath.
- **D4 — Token budgets are first-class.** Per-tier caps enforced in code via a metering wrapper around all model calls. Target 70–80% gross margin after API cost.
- **D5 — Beachhead ICP is mid-market B2B SaaS (Series A–C, $5–50M ARR, 3–15 person marketing teams).** Agencies are the second wedge. Enterprise, sub-$100/mo SMB, and DTC launch are explicitly deferred.
- **D6 — Autonomy defaults to "Review" mode.** Auto-publish and Autopilot ship only after brand-safety guardrails and approval gates exist.
- **D7 — Program to an `AgentRuntime` interface, not to Hermes.** Hermes is the first implementation (`HermesAgentRuntime`), not a permanent dependency. Same logic as the model router one layer down: don't couple the product to a young framework's memory model or scheduler before hitting real multi-tenant load. Swapping it later must mean swapping an implementation, not the product.
- **D8 — First build is Milestone 0, narrowed to one of everything.** One vertical, one domain, one CMS (WordPress), one autonomy mode (Review), one model path (OpenAI via metering wrapper). Prove the loop before breadth. Do not let scope creep back toward the full platform before M0 is done. (Adopted from external review; the critique was correct on scope discipline.)
- **D9 — M0 proof metric is operator credibility, not visibility lift; and staging-first.** Lift is too noisy/confounded on one domain over 30 days (AI non-determinism). M0 proves the loop reliably produces approved, non-breaking, audited, metered work. M0 publishes to staging/draft or our own test sites only — **no customer live-site writes until Phase 1**, after the loop is proven. Visibility lift becomes the Phase 1 metric, measured across enough domains/samples to be meaningful.
- **D10 — Use npm workspaces for the initial scaffold.** `pnpm --version` failed in this managed Windows sandbox with `EPERM` while inspecting `C:\Users\kylel`; npm 11 worked and supports the needed workspace scripts. This is a pragmatic local-tooling choice, not a product architecture decision, and can be revisited if pnpm works cleanly outside the sandbox.

---

## Open Questions / Risks (keep current)

- **Q1:** Final job-orchestration choice — Temporal vs. BullMQ for MVP. Leaning Temporal for durability; confirm when building the monitor→publish loop.
- **Q2:** Cross-language DB access pattern (TS Prisma + Python) — Prisma schema/RLS exists; still need to decide Python DB access for the DB-backed budget repository and runtime writes.
- **Q3:** First CMS integration target confirmed as WordPress; Webflow second. Validate API auth flow before committing the connector interface in `packages/integrations`.
- **Q4:** Per-customer agent isolation model — container-per-customer vs. shared runtime with tenant context. Affects infra cost and blast radius; decide before scaling past design partners.
- **Q5:** Next/PostCSS audit path — npm reports a moderate advisory in Next's nested `postcss@8.4.31`; wait for a non-breaking Next/PostCSS resolution or validate a safe override before production use.
- **Q6:** Production auth provider — Auth.js is installed but currently uses a development credentials provider. Choose production provider/adapter path, likely Auth.js + Prisma-backed lookup, before real customer access.
- **R1 (margin):** Uncontrolled token burn. Mitigation enforced via D4; verify metering works before any auto-publish path goes live.
- **R2 (platform):** AI engine API/policy changes. Mitigation via model-agnostic routing (D2) and multi-engine redundancy.
