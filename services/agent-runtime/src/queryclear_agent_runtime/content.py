from __future__ import annotations

from dataclasses import dataclass, replace
from decimal import Decimal

from .metering import ModelRequest, TokenMeter
from .monitoring import Opportunity
from .providers import ModelProvider, run_model

# Content generation uses a frontier model for quality (content-engine.md).
_CONTENT_MODEL = "gpt-4.1"
_MAX_OUTPUT_TOKENS = 1200


class ApprovalRequired(RuntimeError):
    pass


@dataclass(frozen=True)
class BrandVoice:
    """M0: a brand voice profile as a guideline string. Training the profile from
    the customer's site/docs is P1-6 (content-engine.md)."""

    brand: str
    guidelines: str


@dataclass(frozen=True)
class ContentPiece:
    id: str
    opportunity_id: str
    title: str
    body: str
    status: str  # pending_approval | approved | rejected | published
    model: str
    usage_record_id: str
    cost_usd: Decimal
    reviewer: str | None = None
    review_note: str | None = None
    cms_post_id: str | None = None
    published_at: str | None = None


def _system_prompt(voice: BrandVoice) -> str:
    return (
        f"You write for {voice.brand}. Brand voice: {voice.guidelines} "
        "Write answer-first content: lead with a direct, factual answer, then "
        "support it. Do not fabricate claims, statistics, or testimonials."
    )


def generate_content_draft(
    meter: TokenMeter,
    provider: ModelProvider,
    opportunity: Opportunity,
    voice: BrandVoice,
    *,
    org_id: str,
    domain_id: str,
    model: str = _CONTENT_MODEL,
) -> ContentPiece:
    """Generate ONE brand-voiced draft for a content opportunity, metered, and
    return it awaiting human review."""
    if opportunity.opportunity_type != "content":
        raise ValueError(
            f"content engine only handles 'content' opportunities, got "
            f"{opportunity.opportunity_type!r}"
        )

    prompt = (
        f"Goal: {opportunity.title}\n"
        f"Why this matters: {opportunity.rationale}\n"
        "Write the article."
    )
    request = ModelRequest(
        org_id=org_id,
        domain_id=domain_id,
        task_class="content_generation",
        provider="openai",
        model=model,
        estimated_input_tokens=max(64, len(prompt) // 4),
        max_output_tokens=_MAX_OUTPUT_TOKENS,
    )
    call = run_model(meter, provider, request, prompt, system=_system_prompt(voice))
    return ContentPiece(
        id=f"cp-{opportunity.id}",
        opportunity_id=opportunity.id,
        title=opportunity.title,
        body=call.response.content,
        status="pending_approval",
        model=model,
        usage_record_id=call.budget.usage.id,
        cost_usd=call.response.cost_usd,
    )


def review_content(
    piece: ContentPiece, *, approved: bool, reviewer: str, note: str | None = None
) -> ContentPiece:
    """Record a human review decision (Review-mode approval gate)."""
    return replace(
        piece,
        status="approved" if approved else "rejected",
        reviewer=reviewer,
        review_note=note,
    )


def assert_approved_for_publish(piece: ContentPiece, autonomy_mode: str) -> None:
    """Gate before any publish. M0 supports only Review mode: nothing publishes
    without an explicit human approval."""
    if autonomy_mode != "review":
        raise ApprovalRequired(
            f"autonomy mode {autonomy_mode!r} is not enabled in M0 (Review only)"
        )
    if piece.status != "approved":
        raise ApprovalRequired(
            f"content {piece.id} is {piece.status!r}; Review mode requires approval "
            "before publish"
        )
