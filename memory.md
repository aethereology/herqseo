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

**Phase:** Phase 0 done; **Milestone 0 effectively complete (M0-2..M0-6 done)** — the operator loop runs end to end in code AND through the UI/HTTP boundary. Remaining M0: `M0-1` real Hermes (deferred). Pre-customer: Postgres persistence + DB-backed budget repo; real OpenAI/WordPress validation.
**Last updated:** Session 10 (M0-6 UI + runnable demo service; loop verified over HTTP).
**What runs today:** `npm run ci`, `npm run build`, and `npm run test:py` pass (41 Python tests). Web app: Auth.js sign-in, tenant sessions, protected dashboard with the **operator console** (`OperatorConsole.tsx`: run→review→publish). Agent runtime runs the whole M0 loop (`crawl_site`→`run_monitoring`→`generate_content_draft`→Review gate→`publish_content` draft-only→`AuditEvent`), every model call metered. A runnable FastAPI service (`serve.py` `build_app`, offline demo mode) exposes it; the Next.js console calls it via authenticated proxy routes (`/api/loop/run|review|publish`). Loop verified end to end over HTTP via curl (gate→409, publish→draft, audit usage-linked).
**Next concrete step:** `M0-1` real Hermes-backed `AgentRuntime` once we lock the orchestration shape (LoopService is the de-facto orchestrator now). Before any customer: Postgres persistence for `ContentPiece`/`Opportunity`/`AuditEvent`/`ModelUsage` + DB-backed `BudgetRepository`, and validate the real OpenAI + live WordPress paths. UI is browser-testable via `npm run dev` + running `serve.py`.
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

### Session 5 — M0-2 OpenAI path through the token meter — 2026-06-15
- What I did: implemented `M0-2`. Added `services/agent-runtime/src/queryclear_agent_runtime/providers.py` with a `ModelProvider` protocol, `OpenAIProvider`, a data-driven `OPENAI_PRICING` table + `ModelPricing.cost()`, `UnsupportedModel`, and a `run_model(meter, provider, request, prompt)` helper that is the only sanctioned model-call path (it wraps `TokenMeter.run_metered`). Exported the new symbols from `__init__.py` and declared an optional `openai` extra in `pyproject.toml`.
- Key design choices: the `openai` SDK is **lazily imported** inside `OpenAIProvider._get_client()` so the core package stays importable without the dep or an API key (CI/tests never touch the network — tests inject a fake client). Provider/model are **validated before** any client is built, so `UnsupportedModel` raises offline. Pricing is an in-code table for M0 (pricing-and-tiers.md calls DB-driven config a Phase-1 calibration step). `run_model` enforces budget-then-call ordering: an over-budget request raises `BudgetExceeded` and the provider is never invoked.
- Verification: wrote 6 new tests in `tests/test_providers.py` (cost blending, usage→ModelResponse mapping, unknown-model + non-openai rejection without a client, metered routing, over-budget gating). `npm run ci` green; 11 Python tests pass.
- What's in progress / half-done: `M0-1` `HermesAgentRuntime` is still the in-memory placeholder (no real Hermes). No real OpenAI call exercised end-to-end (no key in this env); only the fake-client path is tested.
- What the next session should do first: `M0-1` real Hermes integration, or `M0-3` crawl→prompts→opportunities wiring `run_model()` for the model calls.
- Gotchas: tests don't `pip install` the package — they `sys.path`-insert `src`. So any top-level import of `openai` in the package would break CI; keep provider SDK imports lazy.

### Session 6 — M0-3 crawl → visibility prompts → opportunities — 2026-06-15
- CTO call: did `M0-3` before `M0-1`. Rationale: the M0 proof metric is operator credibility, and Hermes (D3/D7) contributes nothing to it yet — the in-memory `HermesAgentRuntime` is a fine substrate to run the real loop through now. Evaluate/swap Hermes once M0-3/M0-4 reveal the orchestration shape the loop actually needs.
- Refactor (corrected an M0-2 miss): `run_model` returned only `BudgetState`, discarding the model output — useless to callers. Now returns `ModelCall(response, budget)`; the meter's `UsageRecord` stays content-free. Updated M0-2 tests.
- Added `crawl.py`: `Page`, `SiteSnapshot`, `PageFetcher` protocol, `parse_page` (stdlib `html.parser`, strips script/style, truncates), `crawl_site` (bounded **seed-path fetch**, NOT link-following — link discovery is P1-3), and `HttpPageFetcher` (lazy `httpx`).
- Added `monitoring.py`: `derive_prompts` (deterministic title→query seeding for M0; model-assisted seeding is P1-4), `run_visibility_checks` (samples each prompt N times for non-determinism, brand-substring citation detection, every sample metered via `run_model`, records `usage_record_ids` + raw responses for explainability), `generate_opportunities` (below-threshold gaps → prioritized `content` opportunities, zero-citation = priority 1), and `run_monitoring` orchestrator returning `MonitoringResult`.
- Declared optional extras `openai` and `crawl` (httpx) in `pyproject.toml`; both SDKs lazily imported so core stays importable/offline-testable.
- Verification: 11 new tests (test_crawl.py + test_monitoring.py); `npm run ci` green, 22 Python tests pass.
- What's NOT done: no real OpenAI/HTTP call exercised (no key/network in env — fakes only). Citation detection is naive substring match (no fuzzy/entity matching). `derive_prompts` query template (`"best {title}"`) is a placeholder. Opportunities are deterministic from gaps (no model-assisted prioritization yet — that's P1-5).
- Next session: `M0-4` one brand-voice draft + Review-mode approval gate, then `M0-5` staging publish + audit.
- Gotchas: tests `sys.path`-insert `src` and never `pip install`, so any top-level `import openai`/`import httpx` in the package breaks CI — keep all provider/fetcher SDK imports lazy.

### Session 7 — M0-4 brand-voice draft + Review-mode approval gate — 2026-06-15
- What I did: implemented `M0-4` in `content.py`. `BrandVoice` (guideline string for M0; profile training is P1-6). `generate_content_draft(meter, provider, opportunity, voice, ...)` → frontier model (`gpt-4.1`), answer-first system prompt with anti-fabrication instruction, metered via `run_model` (task_class `content_generation`), returns a `ContentPiece` with status `pending_approval`, `usage_record_id`, and `cost_usd`. Rejects non-`content` opportunities. `review_content(piece, approved=, reviewer=, note=)` records the human decision (approved/rejected + reviewer/note). `assert_approved_for_publish(piece, autonomy_mode)` is the gate the M0-5 publisher must call: in Review mode it raises `ApprovalRequired` unless status is `approved`; any non-review mode raises (auto-publish disabled in M0, per D6/guardrails-before-autonomy).
- Verification: 8 new tests in `tests/test_content.py` (metered draft, brand-voice/opportunity conditioning, non-content rejection, approve/reject, gate blocks unapproved + rejected, allows approved, blocks non-review mode). `npm run ci` green; 30 Python tests pass.
- What's NOT done: no schema/FAQ markup, internal-link suggestions, plagiarism/grounding guardrails (all P1-6 / pre-auto-publish). `ContentPiece` is in-memory only (no DB persistence yet). No real model call exercised (fakes only). Title is reused from the opportunity; no separate SEO title generation.
- Next session: `M0-5` publish APPROVED `ContentPiece` to staging/draft via a CMS connector behind an interface (WordPress first), record audit trail + usage. The publisher MUST call `assert_approved_for_publish` and MUST target staging/draft only (D9 — no live-site writes in M0).
- Gotchas: `ContentPiece` is a frozen dataclass; use `dataclasses.replace` for state transitions (done in `review_content`). Keep CMS SDKs lazily imported like openai/httpx so CI stays offline.

### Session 8 — M0-5 staging publish + audit trail; end-to-end loop proven — 2026-06-15
- What I did: implemented `M0-5` in `publishing.py` and added an end-to-end loop test. `CmsPublisher` Protocol; `WordPressPublisher` (write-only) posts to `POST {base}/wp-json/wp/v2/posts` with HTTP Basic auth (username + WP application password), httpx lazily imported; **draft-only** — `publish()` raises `StagingOnlyError` for any status outside {draft, pending} (enforces D9, no live writes). `publish_content(publisher, piece, *, autonomy_mode, actor, audit_log)` runs `assert_approved_for_publish` FIRST, publishes as draft, transitions the piece to `published` with `cms_post_id`/`published_at`, and appends an `AuditEvent` (entity_type=content_piece, action=publish) whose metadata links the publish to `approved_by` (piece.reviewer) and the metered `usage_record_id`. Added `cms_post_id`/`published_at` fields to `ContentPiece` (defaults None — non-breaking).
- Verification: 5 new publishing tests + 1 full-loop integration test (`test_loop_e2e.py`: crawl→monitor→opportunity→draft→gate-blocks-unapproved→approve→publish-draft, asserting metered (3 model calls recorded) + audited + never-live). `npm run ci` green; 36 Python tests pass. Documented the built connector in `integrations.md`.
- Significance: the M0 operator loop now runs end to end in code — the M0 "Done when" (reliably produces an approved, non-breaking, audited, metered draft published to staging) is met at the runtime layer. NOT yet validated against a real WordPress site or real OpenAI key (fakes only), and nothing is persisted to Postgres yet.
- Modeling note to reconcile at persistence: runtime encodes approval on `ContentPiece` (status `approved`/`rejected` + reviewer), while `data-model.md` keeps ContentPiece.status in {draft|pending_approval|published|failed} and puts approve/reject in a separate `ApprovalEvent`. When DB persistence lands, move approval to `ApprovalEvent` and keep ContentPiece.status to the enum; the `AuditEvent` here is the seed of that table.
- Next session: `M0-6` thin UI + decide the TS↔Python boundary (Q2) — likely a small Python HTTP service the Next.js app calls, or port the M0 loop to TS. Then persistence + `M0-1` Hermes.
- Gotchas: keep all CMS/provider SDK imports lazy (CI never installs them). `ContentPiece` is frozen — use `dataclasses.replace` for the publish transition (done).

### Session 9 — M0-6 backend: LoopService + FastAPI adapter; Q2 resolved — 2026-06-15
- CTO decision (D11): the TS↔Python boundary is a **thin FastAPI service** wrapping the runtime, not a subprocess bridge or a TS port. Keeps Python as source of truth (D1), containerizable for idle-cheap serverless. Resolves Q2.
- What I did: added `service.py` `LoopService` — framework-free in-memory orchestration of the M0 loop (`run` → crawl+monitor+generate draft; `review`; `publish`), with injected meter/provider/fetcher/voice/publisher so it's fully offline-testable. Added `app.py`, a thin FastAPI adapter (`create_app(service)`) exposing `POST /runs`, `GET /drafts/{id}`, `POST /drafts/{id}/review`, `POST /drafts/{id}/publish`, `GET /audit`; maps `ApprovalRequired`→409, `LoopError`→404. Added optional `api` extra (fastapi+uvicorn).
- Verification: 5 new `LoopService` tests (run→opportunity+draft, no-gap→no-draft, publish-before-approve blocked, approve→publish drafts+audits, unknown-draft raises). `npm run ci` green; 41 Python tests. `app.py` is intentionally NOT imported by `__init__`/tests so CI stays offline (fastapi not installed in CI).
- Git: merged the M0-2..M0-5 loop to `main` (ff), deleted `feat/m0-agent-loop`, now on `feat/m0-ui`.
- What's NOT done: the actual Next.js UI; an env-wired real `LoopService` builder; no FastAPI endpoint integration test in CI (would need fastapi installed). Still in-memory only (no DB).
- Next session: build the Next.js M0-6 pages against the FastAPI endpoints + the env service builder; then persistence and `M0-1` Hermes.
- Gotchas: keep `app.py` out of package `__init__` imports forever, or CI breaks (fastapi/pydantic not installed). `LoopService` holds drafts in memory keyed by `ContentPiece.id` (= `cp-{opportunity.id}`); fine for single-instance M0, replace with DB before multi-instance.

### Session 10 — M0-6 UI + runnable demo service; loop verified over HTTP — 2026-06-15
- What I did: built the M0-6 operator console in `apps/web` and made the runtime runnable. Frontend honors the existing design system (paper/ink/moss/lime, hairline borders) rather than introducing a new aesthetic — it's an internal console that must match the dashboard. New files: `src/app/OperatorConsole.tsx` (client; run→opportunities+draft→approve/reject→publish→audit, with loading/error/empty states, status pills, "staging only" guard copy), `src/lib/agent-runtime.ts` (server-side typed client for the FastAPI runtime; `AgentRuntimeError`), `src/lib/api-helpers.ts` (`getApiTenant`/`unauthorized`/`runtimeErrorResponse`), and authenticated proxy routes `src/app/api/loop/{run,review,publish}/route.ts` (tenant injected server-side; browser never calls the runtime directly). `page.tsx` now renders `<OperatorConsole>` in place of the hardcoded review queue. Runtime: added `serve.py` `build_app()` factory with **offline demo mode** (fakes when `OPENAI_API_KEY`/`WORDPRESS_*` unset) so the loop is clickable without credentials (also serves as a sales demo); wires real OpenAIProvider/HttpPageFetcher/WordPressPublisher when env is set. Added WP + token-budget vars to `.env.example`.
- Verification: web `lint`+`typecheck`+`build` pass (loop API routes registered; `/` builds). Ran the demo FastAPI service (`uvicorn ...serve:build_app --factory`) and drove the full loop via curl: run→1 opportunity + pending draft; publish-before-approve→**409** (gate enforced over HTTP); approve→approved; publish→cms status **draft** (staging only), piece published; `/audit`→1 publish event with `usage_record_id` linked. `npm run ci` still green (41 Python tests; fastapi/uvicorn present in env but `app.py`/`serve.py` remain unimported by tests).
- What's NOT done: not exercised against a real OpenAI key or a live WordPress site; not visually browser-tested (in-app browser historically unavailable — verified via build + HTTP). Still in-memory (LoopService holds drafts per process; restart loses state). Real-mode type ignores in `serve.py` are deliberate (duck-typed providers).
- Next session: `M0-1` real Hermes, then persistence (Postgres) + real OpenAI/WordPress validation. To browser-test now: run `serve.py` on :8080 and `npm run dev` in apps/web, sign in with dev creds.
- Gotchas: keep `app.py`/`serve.py` out of package `__init__` and tests (fastapi import). Client console imports runtime types with `import type` only, so no server code is bundled. Next proxy routes use `auth()` (return 401) not `requireTenant()` (which redirects) — redirects are wrong for JSON endpoints.

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
- **D11 — TS↔Python boundary is a thin FastAPI service.** The Next.js control plane talks to the Python agent runtime over HTTP via a thin FastAPI adapter (`services/agent-runtime/app.py`) wrapping the framework-free `LoopService`. Rejected: subprocess/CLI bridge (fragile stdout parsing, poor errors) and porting the loop to TS (duplicates logic, violates D1). Keeps Python as the source of truth and containerizable for idle-cheap serverless. Resolves Q2.
- **D10 — Use npm workspaces for the initial scaffold.** `pnpm --version` failed in this managed Windows sandbox with `EPERM` while inspecting `C:\Users\kylel`; npm 11 worked and supports the needed workspace scripts. This is a pragmatic local-tooling choice, not a product architecture decision, and can be revisited if pnpm works cleanly outside the sandbox.

---

## Open Questions / Risks (keep current)

- **Q1:** Final job-orchestration choice — Temporal vs. BullMQ for MVP. Leaning Temporal for durability; confirm when building the monitor→publish loop.
- **Q2 (RESOLVED — D11):** TS↔Python boundary is a thin FastAPI service. (Still open sub-question: Python *DB* access pattern for the DB-backed budget repository and runtime writes — decide when persistence lands.)
- **Q3:** First CMS integration target confirmed as WordPress; Webflow second. Validate API auth flow before committing the connector interface in `packages/integrations`.
- **Q4:** Per-customer agent isolation model — container-per-customer vs. shared runtime with tenant context. Affects infra cost and blast radius; decide before scaling past design partners.
- **Q5:** Next/PostCSS audit path — npm reports a moderate advisory in Next's nested `postcss@8.4.31`; wait for a non-breaking Next/PostCSS resolution or validate a safe override before production use.
- **Q6:** Production auth provider — Auth.js is installed but currently uses a development credentials provider. Choose production provider/adapter path, likely Auth.js + Prisma-backed lookup, before real customer access.
- **R1 (margin):** Uncontrolled token burn. Mitigation enforced via D4; verify metering works before any auto-publish path goes live.
- **R2 (platform):** AI engine API/policy changes. Mitigation via model-agnostic routing (D2) and multi-engine redundancy.
