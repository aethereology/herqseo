from __future__ import annotations

import sys
import unittest
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from queryclear_agent_runtime import (  # noqa: E402
    BudgetExceeded,
    InMemoryBudgetRepository,
    ModelPricing,
    ModelRequest,
    OpenAIProvider,
    TokenBudget,
    TokenMeter,
    UnsupportedModel,
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
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens


class _FakeResponse:
    def __init__(self, text: str, input_tokens: int, output_tokens: int) -> None:
        self.output_text = text
        self.usage = _FakeUsage(input_tokens, output_tokens)


class _FakeResponses:
    def __init__(self, response: _FakeResponse) -> None:
        self._response = response
        self.calls: list[dict[str, object]] = []

    def create(self, **kwargs: object) -> _FakeResponse:
        self.calls.append(kwargs)
        return self._response


class _FakeOpenAI:
    def __init__(self, response: _FakeResponse) -> None:
        self.responses = _FakeResponses(response)


class ModelPricingTest(unittest.TestCase):
    def test_cost_blends_input_and_output_rates(self) -> None:
        pricing = ModelPricing(Decimal("2.00"), Decimal("8.00"))
        # 1,000,000 input @ $2 + 500,000 output @ $8 = $2.00 + $4.00
        self.assertEqual(pricing.cost(1_000_000, 500_000), Decimal("6.00"))


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
        self.assertEqual(fake.responses.calls[0]["model"], "gpt-4.1-mini")
        self.assertEqual(fake.responses.calls[0]["max_output_tokens"], 200)

    def test_rejects_unknown_model_without_building_client(self) -> None:
        provider = OpenAIProvider()  # no client; must not be needed
        with self.assertRaises(UnsupportedModel):
            provider.complete(_request(model="gpt-9-imaginary"), "x")

    def test_rejects_non_openai_provider(self) -> None:
        provider = OpenAIProvider()
        with self.assertRaises(UnsupportedModel):
            provider.complete(_request(provider="anthropic"), "x")


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

        self.assertEqual(fake.responses.calls, [])
        self.assertEqual(repo.records, [])


if __name__ == "__main__":
    unittest.main()
