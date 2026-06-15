from __future__ import annotations

import re
from dataclasses import dataclass

from .crawl import SiteSnapshot
from .metering import ModelRequest, TokenMeter
from .providers import ModelProvider, run_model

# M0 monitoring runs against the single OpenAI path; treat it as the ChatGPT
# engine probe. Multi-engine sampling is P1-4.
_MONITORING_MODEL = "gpt-4.1-mini"
_MAX_OUTPUT_TOKENS = 256

# Prompt seeding uses a cheap model to turn crawled content into buyer-intent
# queries (see derive_prompts for the deterministic fallback).
_PROMPT_SEEDING_MODEL = "gpt-4.1-mini"
_MAX_SEED_OUTPUT_TOKENS = 300


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
    """Deterministic fallback: seed prompts from crawled page titles.

    Used when model-backed seeding (`generate_prompts`) is unavailable or returns
    nothing, so the loop never dies on a seeding hiccup.
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


def _site_context(snapshot: SiteSnapshot, *, max_pages: int = 5, max_chars: int = 1500) -> str:
    lines: list[str] = []
    for page in snapshot.pages[:max_pages]:
        bits = [page.title, *page.headings]
        line = " — ".join(b for b in bits if b)
        if line:
            lines.append(line)
    return "\n".join(lines)[:max_chars]


def _parse_queries(text: str, max_prompts: int) -> list[str]:
    queries: list[str] = []
    for raw in text.splitlines():
        # strip leading list markers / numbering / markdown, then quotes
        query = re.sub(r"^[\s\-\*\#\d\.\)]+", "", raw).strip().strip("\"'").strip()
        if query:
            queries.append(query)
        if len(queries) >= max_prompts:
            break
    return queries


def generate_prompts(
    meter: TokenMeter,
    provider: ModelProvider,
    snapshot: SiteSnapshot,
    brand: str,
    *,
    org_id: str,
    domain_id: str,
    max_prompts: int = 5,
    model: str = _PROMPT_SEEDING_MODEL,
) -> list[VisibilityPrompt]:
    """Seed visibility prompts as natural buyer-intent queries generated from the
    crawled site (metered). Falls back to `derive_prompts` if there is no site
    context or the model returns nothing parseable."""
    context = _site_context(snapshot)
    if not context:
        return derive_prompts(snapshot, brand, max_prompts=max_prompts)

    prompt = (
        f"A potential buyer is using AI assistants to find solutions like {brand}.\n"
        f"From the company's site content below, write {max_prompts} natural, "
        "buyer-intent search queries they would actually type — category and "
        "problem queries, NOT the brand name. One query per line; no numbering, "
        "no quotes.\n\n"
        f"Site content:\n{context}"
    )
    request = ModelRequest(
        org_id=org_id,
        domain_id=domain_id,
        task_class="classification",
        provider="openai",
        model=model,
        estimated_input_tokens=max(64, len(prompt) // 4),
        max_output_tokens=_MAX_SEED_OUTPUT_TOKENS,
    )
    call = run_model(meter, provider, request, prompt)
    queries = _parse_queries(call.response.content, max_prompts)
    if not queries:
        return derive_prompts(snapshot, brand, max_prompts=max_prompts)
    return [
        VisibilityPrompt(id=f"vp-{i}", query=query, brand=brand)
        for i, query in enumerate(queries)
    ]


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
    prompts = generate_prompts(
        meter, provider, snapshot, brand,
        org_id=org_id, domain_id=domain_id, max_prompts=max_prompts,
    )
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
