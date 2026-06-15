# Pricing, Tiers & Token Budgets

> Pricing is a product surface: tiers map to enforced limits in code. The token budgets below
> are the link between pricing and the metering wrapper (`docs/architecture.md`).

## Tiers

| Tier | Setup fee | Monthly | Domains | Engines | Prompts | Content/mo | Autonomy | Token budget* |
|---|---|---|---|---|---|---|---|---|
| **Operator** | $2,500 | $599 | 1 | 5 | 100 | 8 | Review | low |
| **Growth** (core ICP) | $5,000 | $1,499 | 3 | 8 | 500 | 25 | Auto-publish | mid |
| **Scale** | $10,000 | $3,499 | unlimited | 10+ | 2,000 | 75 | Autopilot | high |
| **Agency Partner** | $7,500 | from $1,999 + $299/client | per-client | 8 | per-client | per-client | configurable | pooled per client |
| **Enterprise** | $25,000+ | $7,500+ | custom | custom | custom | custom | custom | custom |

*Token budget is a concrete monthly cap set so blended COGS keeps gross margin in the **70–80%** band. Calibrate the exact numbers against real per-task token measurements during Phase 1, then encode them as config (not hardcoded) in the metering wrapper.

## How tiers map to enforcement

- `Organization.plan_tier` → resolves to a config object: `{ max_domains, max_engines, max_prompts, max_content_per_month, allowed_autonomy_modes, token_budget_monthly }`.
- The metering wrapper reads `token_budget_monthly` and the running `token_used_current_period`.
- Limits checked at the relevant action (adding a domain, running an engine check, publishing a piece, making a model call).

## Budget-exhaustion behavior

When a customer approaches/exceeds the monthly token budget:
1. **Soft cap (e.g. 80%):** notify; route more work to cheaper models via the router.
2. **Hard cap (100%):** pause non-essential autonomous work; essential monitoring continues at minimum cost.
3. **Overage:** bill via Stripe metered usage (per-token or per-piece), turning excess into revenue, not loss.

Never silently fail — surface budget state in the dashboard.

## Pricing rationale (summary)

- Anchored to **agency replacement** — the buyer's mental model is a $4–12K/mo retainer with a 50–100% setup fee. We sit in the under-served **$500–$2,000/mo "lonely middle."**
- **Setup fee** front-loads cash, funds token-heavy onboarding (audit, brand-voice training, baselining), and filters tire-kickers (paid-setup customers retain ~2–3×).
- **Usage-based overage** is the expansion lever once the predictable base is established.
- Rejected: pure subscription (lengthens CAC payback), pure outcome-based (AI responses non-deterministic — operationally/legally fragile), pure done-for-you services (caps growth, dilutes multiples).

Full reasoning in `docs/strategic-brief.md`.

## Build implications
- Tier config must be **data-driven** (DB/config), not hardcoded, so pricing can evolve without redeploys.
- Stripe products/prices mirror this table; setup fee = one-time, subscription = recurring, overage = metered.
- Token budgets are meaningless without the metering wrapper — build that first (`PROGRESS.md` P0-4).
