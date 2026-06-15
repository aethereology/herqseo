# Spec: Monitoring Engine

**Owns:** measuring brand visibility, citation share, and sentiment across AI engines, and reconciling with analytics.
**Pillar 1** of the product (`docs/product-spec.md`).

## Inputs
- A domain, its brand/competitor set, and a prompt set (seeded from the brand's category + discovered gaps).

## What it does
1. Run a prompt set against each enabled AI engine.
2. For each response, detect: **brand cited?**, citation rank/position, sentiment, and competitors mentioned (share of voice).
3. Store each result as a `VisibilityCheck` with the **raw response reference** (explainability).
4. Reconcile with **GA4 + GSC + CRM** to connect visibility to traffic/pipeline/revenue.
5. Compute trends and feed gaps to the opportunity generator.

## Engines (Phase 1: 5 → Phase 2: 8)
ChatGPT, Google AI Overviews, Google AI Mode, Gemini, Perplexity, Claude, Copilot, Grok (Rufus, Meta AI later).

## Access strategy
- Official APIs where available; compliant query methods otherwise; server-side fallbacks if an API degrades.
- **No single engine may exceed ~30% of delivered value** — keep the set redundant.
- Account for **non-determinism**: the same prompt may not return the same brand twice (SparkToro: <1-in-100 reproducibility). Therefore **sample repeatedly** and report **frequencies with confidence intervals**, never single-shot certainties.

## Outputs
- Visibility score, share-of-voice vs. competitors, sentiment, and prioritized gaps — each traceable to prompt + engine + raw response.
- Baseline + follow-up checks power `LiftMeasurement`.

## Cost discipline
- Monitoring is high-frequency → route to **cheap models** via the router; cache where possible. All calls metered.

## Acceptance criteria (Phase 1)
- For one domain, run a prompt set across 5 engines, produce sampled visibility metrics with confidence intervals, store raw responses, and surface the top gaps to the opportunity generator.
