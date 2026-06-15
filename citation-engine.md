# Spec: Citation Engine

**Owns:** off-page work to get the brand cited in AI answers.
**Pillar 4** of the product (`docs/product-spec.md`). Phase 3.

## What it does
1. **Prompt-gap detection** — find prompts where the brand *should* appear in AI answers but doesn't (fed by the monitoring engine).
2. **Opportunity surfacing** — identify high-leverage citation sources: relevant Reddit threads, YouTube content, Wikipedia entries, industry directories, and authoritative pages AI engines cite.
3. **Outreach** — draft and (with approval) send outreach for citation placement; track responses and outcomes.

## Flow
1. Monitoring engine flags gaps → create `Opportunity` (type=citation).
2. For each, propose a channel + target + action (`CitationCampaign`).
3. Gate by autonomy mode; outreach messages always reviewable.
4. Track outcome; re-check visibility after placement to attribute lift.

## Guardrails
- No spammy or platform-rule-violating behavior (respect Reddit/YouTube/Wikipedia norms and ToS).
- Outreach is transparent and on-brand; never deceptive.
- Human approval required for any external communication until trust is established.

## Cost discipline
- Research/drafting is moderate token use; meter and count against budget.

## Acceptance criteria (Phase 3)
- From a detected prompt gap, surface ranked citation opportunities, draft compliant outreach under the autonomy gate, and track outcomes back to a visibility re-check.
