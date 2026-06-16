from __future__ import annotations

import sys
import threading
import time
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


def _request(reserved_in: int = 10, reserved_out: int = 10) -> ModelRequest:
    return ModelRequest(
        org_id="org",
        domain_id="d",
        task_class="monitoring",
        provider="openai",
        model="m",
        estimated_input_tokens=reserved_in,
        max_output_tokens=reserved_out,
    )


class ConcurrentMeteringTest(unittest.TestCase):
    def test_no_usage_increments_lost_under_concurrency(self) -> None:
        # Without a lock around add_usage, the read-modify-write of used_tokens
        # races and increments are lost (under-billing). This pins atomicity.
        repo = InMemoryBudgetRepository({"org": TokenBudget("org", 10_000_000)})
        meter = TokenMeter(repo)

        def one_call() -> None:
            meter.run_metered(
                _request(), lambda: ModelResponse("ok", 10, 10, Decimal("0"))
            )

        threads = [threading.Thread(target=one_call) for _ in range(50)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(len(repo.records), 50)
        self.assertEqual(repo.get_budget("org").used_tokens, 50 * 20)

    def test_reservation_holds_the_cap_under_concurrency(self) -> None:
        # Budget allows exactly two in-flight reservations of 200 tokens each.
        repo = InMemoryBudgetRepository({"org": TokenBudget("org", 400)})
        meter = TokenMeter(repo)
        release = threading.Event()
        in_invoke: list[int] = []
        guard = threading.Lock()
        results: dict[int, str] = {}

        def call(idx: int) -> None:
            def invoke() -> ModelResponse:
                with guard:
                    in_invoke.append(idx)
                release.wait(5)
                return ModelResponse("ok", 1, 1, Decimal("0"))

            try:
                meter.run_metered(_request(100, 100), invoke)  # reserves 200
                results[idx] = "ok"
            except BudgetExceeded:
                results[idx] = "blocked"

        threads = [threading.Thread(target=call, args=(i,)) for i in range(6)]
        for t in threads:
            t.start()

        # Wait until all six have resolved their reservation attempt: two parked
        # inside invoke (holding 400 reserved), four rejected.
        deadline = time.time() + 5
        while time.time() < deadline:
            if len(in_invoke) == 2 and sum(v == "blocked" for v in results.values()) == 4:
                break
            time.sleep(0.02)
        release.set()
        for t in threads:
            t.join()

        self.assertEqual(sum(v == "ok" for v in results.values()), 2)
        self.assertEqual(sum(v == "blocked" for v in results.values()), 4)
        # only the two that actually ran were billed
        self.assertEqual(len(repo.records), 2)


if __name__ == "__main__":
    unittest.main()
