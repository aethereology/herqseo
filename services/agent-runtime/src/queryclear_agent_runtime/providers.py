from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol

from .metering import BudgetState, ModelRequest, ModelResponse, TokenMeter


class UnsupportedModel(RuntimeError):
    pass


@dataclass(frozen=True)
class ModelPricing:
    """USD price per 1M tokens for a single model."""

    input_per_mtok: Decimal
    output_per_mtok: Decimal

    def cost(self, input_tokens: int, output_tokens: int) -> Decimal:
        million = Decimal(1_000_000)
        return (
            self.input_per_mtok * Decimal(input_tokens) / million
            + self.output_per_mtok * Decimal(output_tokens) / million
        )


# Data-driven for M0; calibrate against real usage and move to config in Phase 1
# (see docs/pricing-and-tiers.md). USD per 1M tokens.
OPENAI_PRICING: dict[str, ModelPricing] = {
    "gpt-4.1": ModelPricing(Decimal("2.00"), Decimal("8.00")),
    "gpt-4.1-mini": ModelPricing(Decimal("0.40"), Decimal("1.60")),
}

ANTHROPIC_PRICING: dict[str, ModelPricing] = {
    "claude-sonnet-4-6": ModelPricing(Decimal("3.00"), Decimal("15.00")),
    "claude-haiku-4-5-20251001": ModelPricing(Decimal("1.00"), Decimal("5.00")),
}


class ModelProvider(Protocol):
    def complete(
        self, request: ModelRequest, prompt: str, *, system: str | None = None
    ) -> ModelResponse:
        ...


class OpenAIProvider:
    """OpenAI-only model path for M0.

    The ``openai`` SDK is imported lazily so the package stays importable without
    the dependency or an API key (e.g. in CI). Injecting ``client`` skips the SDK
    entirely, which keeps tests offline.
    """

    provider_name = "openai"

    def __init__(
        self,
        *,
        api_key: str | None = None,
        client: object | None = None,
        pricing: dict[str, ModelPricing] | None = None,
    ) -> None:
        self._api_key = api_key
        self._client = client
        self._pricing = pricing or OPENAI_PRICING

    def complete(
        self, request: ModelRequest, prompt: str, *, system: str | None = None
    ) -> ModelResponse:
        pricing = self._pricing_for(request)  # validate before any network/SDK use
        client = self._get_client()

        messages: list[dict[str, str]] = []
        if system is not None:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        response = client.chat.completions.create(
            model=request.model,
            messages=messages,
            max_tokens=request.max_output_tokens,
        )
        input_tokens = response.usage.prompt_tokens
        output_tokens = response.usage.completion_tokens
        return ModelResponse(
            content=response.choices[0].message.content,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=pricing.cost(input_tokens, output_tokens),
        )

    def _pricing_for(self, request: ModelRequest) -> ModelPricing:
        if request.provider != self.provider_name:
            raise UnsupportedModel(
                f"OpenAIProvider cannot serve provider {request.provider!r}"
            )
        try:
            return self._pricing[request.model]
        except KeyError as exc:
            raise UnsupportedModel(f"No pricing for model {request.model!r}") from exc

    def _get_client(self):  # type: ignore[no-untyped-def]
        if self._client is None:
            from openai import OpenAI  # lazy: optional dependency

            self._client = OpenAI(api_key=self._api_key)
        return self._client


class AnthropicProvider:
    """Anthropic (Claude) model path — the second provider that proves the
    reasoning brain is model-agnostic (architecture.md). The ``anthropic`` SDK
    is imported lazily so the package stays importable without it; injecting
    ``client`` keeps tests offline.
    """

    provider_name = "anthropic"

    def __init__(
        self,
        *,
        api_key: str | None = None,
        client: object | None = None,
        pricing: dict[str, ModelPricing] | None = None,
    ) -> None:
        self._api_key = api_key
        self._client = client
        self._pricing = pricing or ANTHROPIC_PRICING

    def complete(
        self, request: ModelRequest, prompt: str, *, system: str | None = None
    ) -> ModelResponse:
        pricing = self._pricing_for(request)  # validate before any network/SDK use
        client = self._get_client()

        kwargs: dict[str, object] = {
            "model": request.model,
            "max_tokens": request.max_output_tokens,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system is not None:
            kwargs["system"] = system  # Anthropic takes system as a top-level arg

        response = client.messages.create(**kwargs)
        input_tokens = response.usage.input_tokens
        output_tokens = response.usage.output_tokens
        return ModelResponse(
            content=response.content[0].text,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=pricing.cost(input_tokens, output_tokens),
        )

    def _pricing_for(self, request: ModelRequest) -> ModelPricing:
        if request.provider != self.provider_name:
            raise UnsupportedModel(
                f"AnthropicProvider cannot serve provider {request.provider!r}"
            )
        try:
            return self._pricing[request.model]
        except KeyError as exc:
            raise UnsupportedModel(f"No pricing for model {request.model!r}") from exc

    def _get_client(self):  # type: ignore[no-untyped-def]
        if self._client is None:
            from anthropic import Anthropic  # lazy: optional dependency

            self._client = Anthropic(api_key=self._api_key)
        return self._client


class RoutingProvider:
    """Model-agnostic dispatch: routes each call to the backend registered for
    ``request.provider``. This is the seam that lets QueryClear send each task to
    the best/cheapest provider (architecture.md) without coupling call sites to a
    vendor. Per-task routing *policy* (which provider/model per task_class) is a
    follow-up that sets ``request.provider`` accordingly.
    """

    def __init__(self, backends: dict[str, ModelProvider]) -> None:
        if not backends:
            raise ValueError("RoutingProvider needs at least one backend")
        self._backends = dict(backends)

    def complete(
        self, request: ModelRequest, prompt: str, *, system: str | None = None
    ) -> ModelResponse:
        try:
            backend = self._backends[request.provider]
        except KeyError as exc:
            raise UnsupportedModel(
                f"No provider registered for {request.provider!r}; "
                f"have {sorted(self._backends)}"
            ) from exc
        return backend.complete(request, prompt, system=system)


@dataclass(frozen=True)
class ModelCall:
    """A metered model call: the model's output plus the resulting budget state.

    The meter's ``UsageRecord`` is intentionally content-free, so callers that
    need the actual output read it here.
    """

    response: ModelResponse
    budget: BudgetState


def run_model(
    meter: TokenMeter,
    provider: ModelProvider,
    request: ModelRequest,
    prompt: str,
    *,
    system: str | None = None,
) -> ModelCall:
    """Only sanctioned way to call a model: through the meter and a provider."""
    captured: list[ModelResponse] = []

    def invoke() -> ModelResponse:
        response = provider.complete(request, prompt, system=system)
        captured.append(response)
        return response

    budget = meter.run_metered(request, invoke)
    return ModelCall(response=captured[0], budget=budget)
