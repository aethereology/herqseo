# QueryClear

**The autonomous SEO/AEO/GEO operator for mid-market B2B SaaS.**

QueryClear isn't a dashboard that tells you you're invisible in AI search — it's an agent that does the work: it monitors your brand across AI engines (ChatGPT, Google AI Overviews, Gemini, Perplexity, Claude, Copilot, Grok), generates and publishes answer-first content into your CMS, fixes on-page technical SEO, and runs off-page citation campaigns — autonomously, with human approval gates you control.

> Positioning: **"Searchable tells your team what to do. QueryClear does it."**

## How it works

Every customer gets a **dedicated agent** built on [Hermes Agent](https://hermes-agent.org/) (Nous Research), with persistent memory of their brand, voice, and history. The reasoning brain is **model-agnostic** (OpenAI API by default, routed across providers per task). On top sits QueryClear's proprietary orchestration layer: multi-tenancy, billing, brand-safety guardrails, an autonomy slider, and deep integrations with GA4, Search Console, and your CRM.

## For developers / Claude Code

This repo is set up for agentic development in VSCode/Cursor with Claude Code.

**Start here:**
1. `CLAUDE.md` — project constitution (Claude Code reads this first)
2. `memory.md` — working memory; **update it after every session**
3. `PROGRESS.md` — task tracker

**Then read the specs:**
- Root `*.md` spec files — strategy, architecture, product spec, tech stack, data model, integrations, pricing, roadmap
- Per-engine root spec files — agent layer, orchestration, monitoring, content, technical-SEO, citation

## Development quick start

```sh
npm install
npm run ci
npm run build
cd apps/web
npx next dev -H 127.0.0.1 -p 3000
```

For local auth, copy `.env.example` to `.env.local`, set `AUTH_SECRET`, and use:

```text
Email: operator@queryclear.dev
Access code: queryclear-dev
```

The first auth slice uses an Auth.js credentials provider that creates a tenant-scoped
development session from `QUERYCLEAR_DEV_*` environment values.

Python runtime tests run through:

```sh
npm run test:py
```

## Target repo layout

```
queryclear/
├── apps/web            # Next.js dashboard + marketing + billing
├── apps/api            # Backend API
├── services/agent-runtime   # Python — Hermes per-customer agents
├── packages/shared     # Shared types/contracts
├── packages/integrations    # CMS/GA4/GSC/CRM connectors
├── packages/db         # Prisma schema + RLS policies
├── docs/               # Strategy & specs
└── specs/              # Component specs
```

## Status

Phase 0 scaffold started. The repo now has npm workspaces, a Next.js web app shell,
shared TypeScript contracts, a Prisma/Postgres schema with RLS migration, an
integration boundary package, Auth.js tenant sessions, and a Python
`AgentRuntime`/token-metering foundation.
See `PROGRESS.md` for the active build plan.
