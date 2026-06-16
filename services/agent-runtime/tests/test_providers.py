from __future__ import annotations

import sys
import unittest
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from queryclear_agent_runtime import (  # noqa: E402
    AnthropicProvider,
    BudgetExceeded,
    InMemoryBudgetRepository,
    ModelPricing,
    ModelRequest,
    ModelRoute,
    OpenAIProvider,
    ModelRoutingPolicy,
    RoutingProvider,
    TokenBudget,
    TokenMeter,
    UnsupportedModel,
    resolve_model_route,
    run_model,
)


def _request(model: str = "gpt-4.1-mini", **overrides: object) -> ModelRequest:
    base: dict[str, object] = {
        "org_id": "org_1",
        "domain_id": "domain_1",
        "task_class": "content_generation",
        "provider": "openai",
        "model": model,
        "estimated_input_tokens": 100,
        "max_output_tokens": 200,
    }
    base.update(overrides)
    return ModelRequest(**base)  # type: ignore[arg-type]


class _FakeUsage:
    def __init__(self, input_tokens: int, output_tokens: int) -> None:
        self.prompt_tokens = input_tokens
        self.completion_tokens = output_tokens


class _FakeMessage:
    def __init__(self, content: str) -> None:
        self.content = content


class _FakeChoice:
    def __init__(self, content: str) -> None:
        self.message = _FakeMessage(content)


class _FakeResponse:
    def __init__(self, text: str, input_tokens: int, output_tokens: int) -> None:
        self.choices = [_FakeChoice(text)]
        self.usage = _FakeUsage(input_tokens, output_tokens)


class _FakeCompletions:
    def __init__(self, response: _FakeResponse) -> None:
        self._response = response
        self.calls: list[dict[str, object]] = []

    def create(self, **kwargs: object) -> _FakeResponse:
        self.calls.append(kwargs)
        return self._response


class _FakeOpenAI:
    def __init__(self, response: _FakeResponse) -> None:
        self.chat = type("Chat", (), {"completions": _FakeCompletions(response)})()


class ModelPricingTest(unittest.TestCase):
    def test_cost_blends_input_and_output_rates(self) -> None:
        pricing = ModelPricing(Decimal("2.00"), Decimal("8.00"))
        # 1,000,000 input @ $2 + 500,000 output @ $8 = $2.00 + $4.00
        self.assertEqual(pricing.cost(1_000_000, 500_000), Decimal("6.00"))


class ModelRoutingPolicyTest(unittest.TestCase):
    def test_default_routes_preserve_openai_path(self) -> None:
        policy = ModelRoutingPolicy()

        self.assertEqual(
            policy.route_for("monitoring"),
            ModelRoute(provider="openai", model="gpt-4.1-mini"),
        )
        self.assertEqual(
            policy.route_for("content_generation"),
            ModelRoute(provider="openai", model="gpt-4.1"),
        )

    def test_overrides_task_route(self) -> None:
        policy = ModelRoutingPolicy(
            {"monitoring": ModelRoute(provider="anthropic", model="claude-haiku-4-5-20251001")}
        )

        self.assertEqual(
            policy.route_for("monitoring"),
            ModelRoute(provider="anthropic", model="claude-haiku-4-5-20251001"),
        )
        self.assertEqual(policy.route_for("classification").provider, "openai")

    def test_from_env_parses_provider_model_pairs(self) -> None:
        policy = ModelRoutingPolicy.from_env(
            {"QUERYCLEAR_MODEL_ROUTE_CONTENT_GENERATION": "anthropic:claude-sonnet-4-6"}
        )

        self.assertEqual(
            policy.route_for("content_generation"),
            ModelRoute(provider="anthropic", model="claude-sonnet-4-6"),
        )

    def test_from_env_rejects_invalid_route(self) -> None:
        with self.assertRaises(ValueError):
            ModelRoutingPolicy.from_env({"QUERYCLEAR_MODEL_ROUTE_MONITORING": "openai"})

    def test_unknown_task_raises(self) -> None:
        with self.assertRaises(UnsupportedModel):
            ModelRoutingPolicy().route_for("image_generation")

    def test_model_override_keeps_policy_provider(self) -> None:
        policy = ModelRoutingPolicy(
            {"monitoring": ModelRoute(provider="anthropic", model="claude-haiku-4-5-20251001")}
        )

        route = resolve_model_route("monitoring", policy, model="claude-sonnet-4-6")

        self.assertEqual(route, ModelRoute(provider="anthropic", model="claude-sonnet-4-6"))


class OpenAIProviderTest(unittest.TestCase):
    def test_complete_maps_usage_and_cost(self) -> None:
        fake = _FakeOpenAI(_FakeResponse("hello", input_tokens=120, output_tokens=80))
        provider = OpenAIProvider(client=fake)

        response = provider.complete(_request(), "write a draft")

        self.assertEqual(response.content, "hello")
        self.assertEqual(response.input_tokens, 120)
        self.assertEqual(response.output_tokens, 80)
        # gpt-4.1-mini: 120 in @ $0.40/Mtok + 80 out @ $1.60/Mtok
        self.assertEqual(response.cost_usd, Decimal("0.40") * 120 / 1_000_000 + Decimal("1.60") * 80 / 1_000_000)
        self.assertEqual(fake.chat.completions.calls[0]["model"], "gpt-4.1-mini")
        self.assertEqual(fake.chat.completions.calls[0]["max_tokens"], 200)

    def test_rejects_unknown_model_without_building_client(self) -> None:
        provider = OpenAIProvider()  # no client; must not be needed
        with self.assertRaises(UnsupportedModel):
            provider.complete(_request(model="gpt-9-imaginary"), "x")

    def test_rejects_non_openai_provider(self) -> None:
        provider = OpenAIProvider()
        with self.assertRaises(UnsupportedModel):
            provider.complete(_request(provider="anthropic"), "x")


class _FakeAnthropicUsage:
    def __init__(self, input_tokens: int, output_tokens: int) -> None:
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens


class _FakeTextBlock:
    def __init__(self, text: str) -> None:
        self.text = text


class _FakeAnthropicResponse:
    def __init__(self, text: str, input_tokens: int, output_tokens: int) -> None:
        self.content = [_FakeTextBlock(text)]
        self.usage = _FakeAnthropicUsage(input_tokens, output_tokens)


class _FakeMessages:
    def __init__(self, response: _FakeAnthropicResponse) -> None:
        self._response = response
        self.calls: list[dict[str, object]] = []

    def create(self, **kwargs: object) -> _FakeAnthropicResponse:
        self.calls.append(kwargs)
        return self._response


class _FakeAnthropic:
    def __init__(self, response: _FakeAnthropicResponse) -> None:
        self.messages = _FakeMessages(response)


class AnthropicProviderTest(unittest.TestCase):
    def _req(self, **over: object) -> ModelRequest:
        return _request(model="claude-haiku-4-5-20251001", provider="anthropic", **over)

    def test_complete_maps_usage_cost_and_system_arg(self) -> None:
        fake = _FakeAnthropic(_FakeAnthropicResponse("hi", input_tokens=100, output_tokens=50))
        provider = AnthropicProvider(client=fake)

        response = provider.complete(self._req(), "draft this", system="be terse")

        self.assertEqual(response.content, "hi")
        self.assertEqual(response.input_tokens, 100)
        self.assertEqual(response.output_tokens, 50)
        # claude-haiku: 100 in @ $1.00/Mtok + 50 out @ $5.00/Mtok
        self.assertEqual(
            response.cost_usd,
            Decimal("1.00") * 100 / 1_000_000 + Decimal("5.00") * 50 / 1_000_000,
        )
        call = fake.messages.calls[0]
        self.assertEqual(call["system"], "be terse")  # system is top-level, not a message
        self.assertEqual(call["messages"], [{"role": "user", "content": "draft this"}])

    def test_rejects_non_anthropic_provider_without_client(self) -> None:
        with self.assertRaises(UnsupportedModel):
            AnthropicProvider().complete(_request(provider="openai", model="gpt-4.1"), "x")


class RoutingProviderTest(unittest.TestCase):
    def test_dispatches_by_request_provider(self) -> None:
        openai = OpenAIProvider(client=_FakeOpenAI(_FakeResponse("from-openai", 10, 10)))
        anthropic = AnthropicProvider(client=_FakeAnthropic(_FakeAnthropicResponse("from-claude", 10, 10)))
        router = RoutingProvider({"openai": openai, "anthropic": anthropic})

        oa = router.complete(_request(provider="openai"), "x")
        an = router.complete(_request(provider="anthropic", model="claude-haiku-4-5-20251001"), "x")

        self.assertEqual(oa.content, "from-openai")
        self.assertEqual(an.content, "from-claude")

    def test_unknown_provider_raises(self) -> None:
        router = RoutingProvider({"openai": OpenAIProvider()})
        with self.assertRaises(UnsupportedModel):
            router.complete(_request(provider="gemini", model="x"), "x")

    def test_requires_at_least_one_backend(self) -> None:
        with self.assertRaises(ValueError):
            RoutingProvider({})


class RunModelTest(unittest.TestCase):
    def test_routes_provider_call_through_meter(self) -> None:
        repo = InMemoryBudgetRepository({"org_1": TokenBudget("org_1", 1000)})
        meter = TokenMeter(repo)
        provider = OpenAIProvider(client=_FakeOpenAI(_FakeResponse("ok", 90, 60)))

        call = run_model(meter, provider, _request(), "generate")

        self.assertEqual(call.response.content, "ok")
        self.assertEqual(call.budget.budget.used_tokens, 150)
        self.assertEqual(repo.records[0].provider, "openai")
        self.assertEqual(repo.records[0].output_tokens, 60)

    def test_does_not_call_provider_when_over_budget(self) -> None:
        repo = InMemoryBudgetRepository({"org_1": TokenBudget("org_1", 100, 50)})
        meter = TokenMeter(repo)
        fake = _FakeOpenAI(_FakeResponse("should not run", 90, 60))
        provider = OpenAIProvider(client=fake)

        with self.assertRaises(BudgetExceeded):
            run_model(meter, provider, _request(), "generate")

        self.assertEqual(fake.chat.completions.calls, [])
        self.assertEqual(repo.records, [])


if __name__ == "__main__":
    unittest.main()
