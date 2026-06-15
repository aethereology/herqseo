from __future__ import annotations

import sys
import unittest
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from queryclear_agent_runtime import (  # noqa: E402
    BudgetExceeded,
    InMemoryBudgetRepository,
    ModelRequest,
    ModelResponse,
    TokenBudget,
    TokenMeter,
)


class TokenMeterTest(unittest.TestCase):
    def test_records_model_usage(self) -> None:
        repo = InMemoryBudgetRepository({"org_1": TokenBudget("org_1", 1000)})
        meter = TokenMeter(repo)

        state = meter.run_metered(
            ModelRequest(
                org_id="org_1",
                domain_id="domain_1",
                task_class="monitoring",
                provider="openai",
                model="gpt-4.1-mini",
                estimated_input_tokens=100,
                max_output_tokens=200,
            ),
            lambda: ModelResponse(
                content="ok",
                input_tokens=90,
                output_tokens=120,
                cost_usd=Decimal("0.0012"),
            ),
        )

        self.assertEqual(state.budget.used_tokens, 210)
        self.assertEqual(repo.records[0].provider, "openai")
        self.assertFalse(state.soft_cap_reached)

    def test_rejects_call_when_reservation_exceeds_budget(self) -> None:
        repo = InMemoryBudgetRepository({"org_1": TokenBudget("org_1", 100, 50)})
        meter = TokenMeter(repo)

        with self.assertRaises(BudgetExceeded):
            meter.run_metered(
                ModelRequest(
                    org_id="org_1",
                    domain_id="domain_1",
                    task_class="content_generation",
                    provider="openai",
                    model="gpt-4.1",
                    estimated_input_tokens=25,
                    max_output_tokens=50,
                ),
                lambda: ModelResponse(
                    content="should not run",
                    input_tokens=25,
                    output_tokens=50,
                    cost_usd=Decimal("0.0100"),
                ),
            )

        self.assertEqual(repo.records, [])

    def test_flags_soft_cap_after_recording_usage(self) -> None:
        repo = InMemoryBudgetRepository({"org_1": TokenBudget("org_1", 1000, 700)})
        meter = TokenMeter(repo)

        state = meter.run_metered(
            ModelRequest(
                org_id="org_1",
                domain_id="domain_1",
                task_class="classification",
                provider="openai",
                model="gpt-4.1-mini",
                estimated_input_tokens=50,
                max_output_tokens=100,
            ),
            lambda: ModelResponse(
                content="ok",
                input_tokens=40,
                output_tokens=80,
                cost_usd=Decimal("0.0008"),
            ),
        )

        self.assertTrue(state.soft_cap_reached)
        self.assertEqual(state.budget.used_tokens, 820)


if __name__ == "__main__":
    unittest.main()
