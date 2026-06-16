from __future__ import annotations

from dataclasses import dataclass, replace
from decimal import Decimal
from uuid import uuid4

from .crawl import SiteSnapshot
from .metering import ModelRequest, TokenMeter
from .monitoring import Opportunity
from .providers import ModelProvider, run_model

# Content generation uses a frontier model for quality (content-engine.md).
_CONTENT_MODEL = "gpt-4.1"
_MAX_OUTPUT_TOKENS = 1200

# Brand-voice derivation is a cheap analysis task (a short style guide).
_VOICE_MODEL = "gpt-4.1-mini"
_VOICE_MAX_OUTPUT_TOKENS = 200
_MIN_VOICE_CORPUS = 200  # chars of site copy below which there's too little signal
_DEFAULT_VOICE_GUIDELINES = (
    "Clear, professional, and concrete. Answer-first. Avoid hype and filler."
)


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
    org_id: str
    domain_id: str
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


def _voice_corpus(
    snapshot: SiteSnapshot, *, max_pages: int = 5, per_page: int = 400, max_chars: int = 1800
) -> str:
    """Representative prose from the site — body text reveals voice better than
    titles/headings alone."""
    parts: list[str] = []
    for page in snapshot.pages[:max_pages]:
        text = f"{page.title}. {page.text}".strip(". ").strip() if page.title else page.text
        if text:
            parts.append(text[:per_page])
    return "\n\n".join(parts)[:max_chars]


def derive_brand_voice(
    meter: TokenMeter,
    provider: ModelProvider,
    snapshot: SiteSnapshot,
    brand: str,
    *,
    org_id: str,
    domain_id: str,
    fallback: str = _DEFAULT_VOICE_GUIDELINES,
    model: str = _VOICE_MODEL,
) -> BrandVoice:
    """Derive a brand-voice profile from the brand's OWN site copy (metered), so
    generated content matches how they actually write — the "training" step of
    the content engine (content-engine.md / P1-6). Falls back to ``fallback``
    guidelines when the site has too little text or the model returns nothing."""
    corpus = _voice_corpus(snapshot)
    if len(corpus) < _MIN_VOICE_CORPUS:
        return BrandVoice(brand=brand, guidelines=fallback)

    prompt = (
        f"Below is copy from {brand}'s website. Describe their brand voice as a "
        "concise, concrete style guide (2–3 sentences): tone, vocabulary, typical "
        "sentence length, and what to avoid. Output only the guideline text.\n\n"
        f"{corpus}"
    )
    request = ModelRequest(
        org_id=org_id,
        domain_id=domain_id,
        task_class="classification",
        provider="openai",
        model=model,
        estimated_input_tokens=max(64, len(prompt) // 4),
        max_output_tokens=_VOICE_MAX_OUTPUT_TOKENS,
    )
    call = run_model(
        meter, provider, request, prompt,
        system="You are a brand-voice analyst. Output only the style guide, no preamble.",
    )
    guidelines = call.response.content.strip()
    return BrandVoice(brand=brand, guidelines=guidelines or fallback)


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
        id=str(uuid4()),
        org_id=org_id,
        domain_id=domain_id,
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
