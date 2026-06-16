from __future__ import annotations

import math
import re
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol
from uuid import uuid4

from .crawl import SiteSnapshot
from .metering import ModelRequest, TokenMeter
from .providers import ModelProvider, ModelRoutingPolicy, resolve_model_route, run_model

_TASK_CLASSIFICATION = "classification"
_TASK_MONITORING = "monitoring"
_MAX_OUTPUT_TOKENS = 256

_MAX_SEED_OUTPUT_TOKENS = 300

AI_ENGINES: tuple[str, ...] = (
    "chatgpt",
    "google_ai_overviews",
    "google_ai_mode",
    "gemini",
    "perplexity",
    "claude",
    "copilot",
    "grok",
)

DEFAULT_MONITORING_ENGINES: tuple[str, ...] = AI_ENGINES[:5]


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
    engine: str = "chatgpt"
    # Honesty contract: True only when the response came from a real, compliant
    # query to the engine itself. False = a model standing in for the engine
    # (an estimate, not a measurement). All current checks are proxy estimates.
    measured: bool = False

    @property
    def citation_frequency(self) -> float:
        return self.cited_count / self.samples if self.samples else 0.0

    @property
    def citation_confidence_interval(self) -> tuple[float, float]:
        """Wilson 95% interval for non-deterministic AI citation sampling."""
        if self.samples <= 0:
            return (0.0, 0.0)
        z = 1.96
        n = self.samples
        p = self.citation_frequency
        denominator = 1 + z**2 / n
        centre = p + z**2 / (2 * n)
        margin = z * math.sqrt((p * (1 - p) + z**2 / (4 * n)) / n)
        low = (centre - margin) / denominator
        high = (centre + margin) / denominator
        return (max(0.0, low), min(1.0, high))

    @property
    def share_of_voice(self) -> Decimal:
        return Decimal(str(round(self.citation_frequency, 4)))


@dataclass(frozen=True)
class Opportunity:
    id: str
    opportunity_type: str  # content | technical | citation (see packages/shared)
    title: str
    rationale: str
    priority: int  # 1 = highest
    prompt_id: str | None
    status: str = "proposed"
    source_engine: str | None = None


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


def parse_monitoring_engines(raw: str | None) -> tuple[str, ...]:
    if not raw:
        return DEFAULT_MONITORING_ENGINES
    engines = tuple(engine.strip() for engine in raw.split(",") if engine.strip())
    unknown = [engine for engine in engines if engine not in AI_ENGINES]
    if unknown:
        raise ValueError(
            f"Unknown monitoring engine(s): {', '.join(unknown)}. "
            f"Allowed: {', '.join(AI_ENGINES)}"
        )
    return engines or DEFAULT_MONITORING_ENGINES


def generate_prompts(
    meter: TokenMeter,
    provider: ModelProvider,
    snapshot: SiteSnapshot,
    brand: str,
    *,
    org_id: str,
    domain_id: str,
    max_prompts: int = 5,
    routing_policy: ModelRoutingPolicy | None = None,
    model: str | None = None,
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
    route = resolve_model_route(_TASK_CLASSIFICATION, routing_policy, model=model)
    request = ModelRequest(
        org_id=org_id,
        domain_id=domain_id,
        task_class=_TASK_CLASSIFICATION,
        provider=route.provider,
        model=route.model,
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


@dataclass(frozen=True)
class EngineProbe:
    """One engine response for one query, with a trace back to its cost."""

    content: str
    usage_record_id: str


class EngineAdapter(Protocol):
    """How we obtain an answer-engine response for a query.

    This is the seam real per-engine adapters drop into. `measured` is the
    honesty contract (mirrored onto `VisibilityCheck.measured`): True only when
    the response is a real, compliant query to the engine itself; False when a
    model is standing in for the engine (an estimate, not a measurement).
    """

    engine: str
    measured: bool

    def probe(self, query: str) -> EngineProbe: ...


class ModelProxyAdapter:
    """A routed model role-playing an answer engine.

    This is what every engine uses until a real, compliant adapter exists for
    it. Asking one model to answer "as Perplexity would" is an honest *estimate*
    of the answer space — it is NOT a measurement of that engine, so
    `measured` is always False and the product must label it as such.
    """

    measured = False

    def __init__(
        self,
        meter: TokenMeter,
        provider: ModelProvider,
        *,
        org_id: str,
        domain_id: str,
        engine: str,
        routing_policy: ModelRoutingPolicy | None = None,
        model: str | None = None,
    ) -> None:
        if engine not in AI_ENGINES:
            raise ValueError(f"Unknown monitoring engine {engine!r}")
        self.engine = engine
        self._meter = meter
        self._provider = provider
        self._org_id = org_id
        self._domain_id = domain_id
        self._route = resolve_model_route(_TASK_MONITORING, routing_policy, model=model)

    def probe(self, query: str) -> EngineProbe:
        probe = (
            f"Engine: {self.engine}\n"
            f"User query: {query}\n\n"
            "Answer the user query as that AI answer surface would. Include "
            "the brands or sources you would cite."
        )
        request = ModelRequest(
            org_id=self._org_id,
            domain_id=self._domain_id,
            task_class=_TASK_MONITORING,
            provider=self._route.provider,
            model=self._route.model,
            estimated_input_tokens=max(32, len(probe) // 4),
            max_output_tokens=_MAX_OUTPUT_TOKENS,
        )
        call = run_model(self._meter, self._provider, request, probe)
        return EngineProbe(content=call.response.content, usage_record_id=call.budget.usage.id)


def build_proxy_adapters(
    meter: TokenMeter,
    provider: ModelProvider,
    *,
    org_id: str,
    domain_id: str,
    engines: Sequence[str] = DEFAULT_MONITORING_ENGINES,
    routing_policy: ModelRoutingPolicy | None = None,
    model: str | None = None,
) -> list[EngineAdapter]:
    """One `ModelProxyAdapter` per engine label — the default until real
    adapters are wired."""
    return [
        ModelProxyAdapter(
            meter,
            provider,
            org_id=org_id,
            domain_id=domain_id,
            engine=engine,
            routing_policy=routing_policy,
            model=model,
        )
        for engine in engines
    ]


def run_visibility_checks(
    meter: TokenMeter,
    provider: ModelProvider,
    org_id: str,
    domain_id: str,
    prompts: list[VisibilityPrompt],
    *,
    samples: int = 3,
    engines: Sequence[str] = DEFAULT_MONITORING_ENGINES,
    adapters: Sequence[EngineAdapter] | None = None,
    routing_policy: ModelRoutingPolicy | None = None,
    model: str | None = None,
) -> list[VisibilityCheck]:
    """Probe brand citation for each prompt, sampling repeatedly for
    non-determinism. Every sample is metered.

    Engines are queried through `EngineAdapter`s. When `adapters` is not given,
    one `ModelProxyAdapter` is built per `engines` label — honest estimates that
    carry `measured=False`. Pass real adapters to get true measurements.
    """
    if adapters is None:
        adapters = build_proxy_adapters(
            meter,
            provider,
            org_id=org_id,
            domain_id=domain_id,
            engines=engines,
            routing_policy=routing_policy,
            model=model,
        )
    checks: list[VisibilityCheck] = []
    for adapter in adapters:
        for prompt in prompts:
            cited = 0
            raw: list[str] = []
            usage_ids: list[str] = []
            needle = prompt.brand.lower()
            for _ in range(samples):
                probe = adapter.probe(prompt.query)
                raw.append(probe.content)
                usage_ids.append(probe.usage_record_id)
                if needle in probe.content.lower():
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
                    engine=adapter.engine,
                    measured=adapter.measured,
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
                id=str(uuid4()),
                opportunity_type="content",
                title=f"Improve {check.engine} visibility for: {check.query}",
                rationale=(
                    f"On {check.engine}, brand '{check.brand}' cited in "
                    f"{check.cited_count}/{check.samples} samples ({freq:.0%}); "
                    f"below the {threshold:.0%} target."
                ),
                priority=priority,
                prompt_id=check.prompt_id,
                source_engine=check.engine,
            )
        )
    opportunities.sort(key=lambda o: (o.priority, o.prompt_id or "", o.source_engine or ""))
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
    engines: Sequence[str] = DEFAULT_MONITORING_ENGINES,
    routing_policy: ModelRoutingPolicy | None = None,
    model: str | None = None,
    max_prompts: int = 5,
    threshold: float = 0.5,
) -> MonitoringResult:
    """The M0-3 loop: crawled site -> seeded prompts -> metered visibility
    checks -> prioritized opportunities."""
    prompts = generate_prompts(
        meter, provider, snapshot, brand,
        org_id=org_id, domain_id=domain_id, max_prompts=max_prompts,
        routing_policy=routing_policy,
    )
    checks = run_visibility_checks(
        meter, provider, org_id, domain_id, prompts, samples=samples,
        engines=engines,
        routing_policy=routing_policy, model=model,
    )
    opportunities = generate_opportunities(checks, threshold=threshold)
    usage_ids = tuple(uid for check in checks for uid in check.usage_record_ids)
    return MonitoringResult(
        checks=tuple(checks),
        opportunities=tuple(opportunities),
        usage_record_ids=usage_ids,
    )
