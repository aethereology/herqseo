from __future__ import annotations

import sys
import unittest
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from queryclear_agent_runtime import (  # noqa: E402
    InMemoryBudgetRepository,
    ModelResponse,
    Page,
    SiteSnapshot,
    TokenBudget,
    TokenMeter,
    VisibilityCheck,
    VisibilityPrompt,
    derive_prompts,
    generate_opportunities,
    run_monitoring,
    run_visibility_checks,
)


class _FakeProvider:
    """Returns scripted content per query so we can simulate citation/no-citation."""

    def __init__(self, responder) -> None:  # responder: Callable[[str], str]
        self._responder = responder
        self.calls: list[str] = []

    def complete(self, request, prompt, *, system=None) -> ModelResponse:
        self.calls.append(prompt)
        return ModelResponse(
            content=self._responder(prompt),
            input_tokens=10,
            output_tokens=10,
            cost_usd=Decimal("0.0001"),
        )


def _snapshot() -> SiteSnapshot:
    return SiteSnapshot(
        domain="https://example.com",
        pages=(
            Page("https://example.com/", "Invoice Automation for SaaS", (), "..."),
            Page("https://example.com/pricing", "Pricing", (), "..."),
            Page("https://example.com/blank", "", (), "no title here"),
        ),
    )


def _meter(budget: int = 1_000_000) -> tuple[TokenMeter, InMemoryBudgetRepository]:
    repo = InMemoryBudgetRepository({"org_1": TokenBudget("org_1", budget)})
    return TokenMeter(repo), repo


class DerivePromptsTest(unittest.TestCase):
    def test_one_prompt_per_titled_page_carrying_brand(self) -> None:
        prompts = derive_prompts(_snapshot(), brand="QueryClear")

        self.assertEqual(len(prompts), 2)  # the untitled page is skipped
        self.assertTrue(all(isinstance(p, VisibilityPrompt) for p in prompts))
        self.assertTrue(all(p.brand == "QueryClear" for p in prompts))
        self.assertIn("invoice automation for saas", prompts[0].query.lower())

    def test_respects_max_prompts(self) -> None:
        prompts = derive_prompts(_snapshot(), brand="QueryClear", max_prompts=1)
        self.assertEqual(len(prompts), 1)


class RunVisibilityChecksTest(unittest.TestCase):
    def test_counts_citations_and_meters_every_sample(self) -> None:
        meter, repo = _meter()
        provider = _FakeProvider(lambda q: "You should try QueryClear for that.")
        prompts = [VisibilityPrompt("vp-0", "best invoice automation", "QueryClear")]

        checks = run_visibility_checks(
            meter, provider, "org_1", "domain_1", prompts, samples=3
        )

        self.assertEqual(len(checks), 1)
        check = checks[0]
        self.assertEqual(check.samples, 3)
        self.assertEqual(check.cited_count, 3)
        self.assertEqual(check.citation_frequency, 1.0)
        self.assertEqual(len(check.raw_responses), 3)
        self.assertEqual(len(check.usage_record_ids), 3)
        # every sample went through the meter
        self.assertEqual(len(repo.records), 3)
        self.assertTrue(all(r.task_class == "monitoring" for r in repo.records))

    def test_detects_absence_of_brand(self) -> None:
        meter, _ = _meter()
        provider = _FakeProvider(lambda q: "I'd recommend a competitor instead.")
        prompts = [VisibilityPrompt("vp-0", "best invoice automation", "QueryClear")]

        checks = run_visibility_checks(meter, provider, "org_1", "domain_1", prompts, samples=2)

        self.assertEqual(checks[0].cited_count, 0)
        self.assertEqual(checks[0].citation_frequency, 0.0)


class GenerateOpportunitiesTest(unittest.TestCase):
    def test_creates_opportunity_only_below_threshold(self) -> None:
        gap = VisibilityCheck("vp-0", "best X", "QueryClear", samples=4, cited_count=1,
                              raw_responses=(), usage_record_ids=())
        strong = VisibilityCheck("vp-1", "best Y", "QueryClear", samples=4, cited_count=4,
                                 raw_responses=(), usage_record_ids=())

        opps = generate_opportunities([gap, strong], threshold=0.5)

        self.assertEqual(len(opps), 1)
        self.assertEqual(opps[0].prompt_id, "vp-0")
        self.assertEqual(opps[0].opportunity_type, "content")
        self.assertEqual(opps[0].status, "proposed")
        self.assertIn("best X", opps[0].title)

    def test_zero_citation_is_highest_priority(self) -> None:
        zero = VisibilityCheck("vp-0", "q", "B", samples=3, cited_count=0,
                               raw_responses=(), usage_record_ids=())
        some = VisibilityCheck("vp-1", "q2", "B", samples=4, cited_count=1,
                               raw_responses=(), usage_record_ids=())

        opps = generate_opportunities([some, zero], threshold=0.5)

        self.assertEqual(opps[0].prompt_id, "vp-0")  # zero-citation sorted first
        self.assertLess(opps[0].priority, opps[1].priority)


class RunMonitoringTest(unittest.TestCase):
    def test_end_to_end_crawl_to_opportunities(self) -> None:
        meter, repo = _meter()

        def responder(prompt: str) -> str:
            # brand cited for the pricing query, invisible for invoice automation
            return "Try QueryClear." if "pricing" in prompt.lower() else "Use something else."

        provider = _FakeProvider(responder)

        result = run_monitoring(
            meter, provider, _snapshot(), brand="QueryClear",
            org_id="org_1", domain_id="domain_1", samples=2,
        )

        self.assertEqual(len(result.checks), 2)  # 2 titled pages
        self.assertEqual(len(repo.records), 4)  # 2 prompts x 2 samples, all metered
        self.assertEqual(len(result.usage_record_ids), 4)
        # only the invisible query produces an opportunity
        self.assertEqual(len(result.opportunities), 1)
        self.assertIn("invoice automation", result.opportunities[0].title.lower())


if __name__ == "__main__":
    unittest.main()
