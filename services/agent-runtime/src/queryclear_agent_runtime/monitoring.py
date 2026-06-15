from __future__ import annotations

from dataclasses import dataclass

from .crawl import SiteSnapshot
from .metering import ModelRequest, TokenMeter
from .providers import ModelProvider, run_model

# M0 monitoring runs against the single OpenAI path; treat it as the ChatGPT
# engine probe. Multi-engine sampling is P1-4.
_MONITORING_MODEL = "gpt-4.1-mini"
_MAX_OUTPUT_TOKENS = 256


@dataclass(frozen=True)
class VisibilityPrompt:
    id: str
    query: str
    brand: str


@dataclass(frozen=True)
class VisibilityCheck:
    prompt_id: str
    query: str
    brand: str
    samples: int
    cited_count: int
    raw_responses: tuple[str, ...]
    usage_record_ids: tuple[str, ...]

    @property
    def citation_frequency(self) -> float:
        return self.cited_count / self.samples if self.samples else 0.0


@dataclass(frozen=True)
class Opportunity:
    id: str
    opportunity_type: str  # content | technical | citation (see packages/shared)
    title: str
    rationale: str
    priority: int  # 1 = highest
    prompt_id: str | None
    status: str = "proposed"


@dataclass(frozen=True)
class MonitoringResult:
    checks: tuple[VisibilityCheck, ...]
    opportunities: tuple[Opportunity, ...]
    usage_record_ids: tuple[str, ...]


def derive_prompts(
    snapshot: SiteSnapshot, brand: str, *, max_prompts: int = 5
) -> list[VisibilityPrompt]:
    """Seed visibility prompts from crawled page titles.

    M0 uses a deterministic template; model-assisted prompt seeding from the
    brand's category and discovered gaps is P1-4 (see monitoring-engine.md).
    """
    prompts: list[VisibilityPrompt] = []
    for page in snapshot.pages:
        if not page.title:
            continue
        prompts.append(
            VisibilityPrompt(
                id=f"vp-{len(prompts)}",
                query=f"best {page.title.lower()}",
                brand=brand,
            )
        )
        if len(prompts) >= max_prompts:
            break
    return prompts


def run_visibility_checks(
    meter: TokenMeter,
    provider: ModelProvider,
    org_id: str,
    domain_id: str,
    prompts: list[VisibilityPrompt],
    *,
    samples: int = 3,
    model: str = _MONITORING_MODEL,
) -> list[VisibilityCheck]:
    """Probe brand citation for each prompt, sampling repeatedly for
    non-determinism. Every sample is metered."""
    checks: list[VisibilityCheck] = []
    for prompt in prompts:
        request = ModelRequest(
            org_id=org_id,
            domain_id=domain_id,
            task_class="monitoring",
            provider="openai",
            model=model,
            estimated_input_tokens=max(16, len(prompt.query) // 4),
            max_output_tokens=_MAX_OUTPUT_TOKENS,
        )
        cited = 0
        raw: list[str] = []
        usage_ids: list[str] = []
        needle = prompt.brand.lower()
        for _ in range(samples):
            call = run_model(meter, provider, request, prompt.query)
            content = call.response.content
            raw.append(content)
            usage_ids.append(call.budget.usage.id)
            if needle in content.lower():
                cited += 1
        checks.append(
            VisibilityCheck(
                prompt_id=prompt.id,
                query=prompt.query,
                brand=prompt.brand,
                samples=samples,
                cited_count=cited,
                raw_responses=tuple(raw),
                usage_record_ids=tuple(usage_ids),
            )
        )
    return checks


def generate_opportunities(
    checks: list[VisibilityCheck], *, threshold: float = 0.5
) -> list[Opportunity]:
    """Turn below-threshold visibility gaps into prioritized, explainable
    content opportunities."""
    opportunities: list[Opportunity] = []
    for check in checks:
        freq = check.citation_frequency
        if freq >= threshold:
            continue
        priority = 1 if check.cited_count == 0 else 2
        opportunities.append(
            Opportunity(
                id=f"opp-{check.prompt_id}",
                opportunity_type="content",
                title=f"Improve AI visibility for: {check.query}",
                rationale=(
                    f"Brand '{check.brand}' cited in {check.cited_count}/{check.samples} "
                    f"samples ({freq:.0%}); below the {threshold:.0%} target."
                ),
                priority=priority,
                prompt_id=check.prompt_id,
            )
        )
    opportunities.sort(key=lambda o: (o.priority, o.prompt_id or ""))
    return opportunities


def run_monitoring(
    meter: TokenMeter,
    provider: ModelProvider,
    snapshot: SiteSnapshot,
    brand: str,
    *,
    org_id: str,
    domain_id: str,
    samples: int = 3,
    model: str = _MONITORING_MODEL,
    max_prompts: int = 5,
    threshold: float = 0.5,
) -> MonitoringResult:
    """The M0-3 loop: crawled site -> seeded prompts -> metered visibility
    checks -> prioritized opportunities."""
    prompts = derive_prompts(snapshot, brand, max_prompts=max_prompts)
    checks = run_visibility_checks(
        meter, provider, org_id, domain_id, prompts, samples=samples, model=model
    )
    opportunities = generate_opportunities(checks, threshold=threshold)
    usage_ids = tuple(uid for check in checks for uid in check.usage_record_ids)
    return MonitoringResult(
        checks=tuple(checks),
        opportunities=tuple(opportunities),
        usage_record_ids=usage_ids,
    )
