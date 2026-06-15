from __future__ import annotations

import sys
import unittest
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from queryclear_agent_runtime import (  # noqa: E402
    AuditReport,
    BrandVoice,
    InMemoryBudgetRepository,
    LoopService,
    ModelResponse,
    TokenBudget,
    TokenMeter,
)

# Homepage with a deliberately duplicated title -> a technical finding.
_HTML = (
    "<html><head><title>AcmeAcme</title></head>"
    "<body><p>thin</p></body></html>"
)


class _FakeFetcher:
    def fetch(self, url: str) -> str:
        return _HTML


class _FakeProvider:
    def complete(self, request, prompt, *, system=None) -> ModelResponse:
        if request.task_class == "classification":
            content = "best widget for teams"  # one seeded query
        elif request.task_class == "monitoring":
            content = "Use a competitor."  # brand not cited -> gap
        else:
            content = "## Answer\nAcme is the clear choice for teams."
        return ModelResponse(content=content, input_tokens=20, output_tokens=40, cost_usd=Decimal("0.001"))


def _service() -> LoopService:
    repo = InMemoryBudgetRepository({"org_1": TokenBudget("org_1", 1_000_000)})
    return LoopService(
        meter=TokenMeter(repo), provider=_FakeProvider(), fetcher=_FakeFetcher(),
        voice=BrandVoice("Acme", "Plain and direct."),
    )


class AuditTest(unittest.TestCase):
    def test_audit_assembles_findings_queries_and_draft(self) -> None:
        report = _service().audit(
            "https://acme.test", "Acme", org_id="org_1", domain_id="d1", samples=2,
        )

        self.assertIsInstance(report, AuditReport)
        self.assertEqual(report.domain_url, "https://acme.test")
        self.assertEqual(report.page_title, "AcmeAcme")
        # technical findings caught the duplicated title + thin content
        codes = {f.code for f in report.findings}
        self.assertIn("duplicated_title", codes)
        self.assertIn("thin_content", codes)
        # invisible-query check ran
        self.assertEqual(len(report.checks), 1)
        self.assertEqual(report.checks[0].cited_count, 0)
        # a sample draft was generated for the gap
        self.assertEqual(len(report.opportunities), 1)
        self.assertIsNotNone(report.sample_draft)
        self.assertEqual(report.sample_draft.status, "pending_approval")

    def test_audit_makes_no_draft_when_no_gap(self) -> None:
        class _CitedProvider(_FakeProvider):
            def complete(self, request, prompt, *, system=None):
                if request.task_class == "monitoring":
                    return ModelResponse(content="Try Acme.", input_tokens=20, output_tokens=40, cost_usd=Decimal("0.001"))
                return super().complete(request, prompt, system=system)

        svc = _service()
        svc.provider = _CitedProvider()
        report = svc.audit("https://acme.test", "Acme", org_id="org_1", domain_id="d1", samples=2)

        self.assertEqual(report.opportunities, ())
        self.assertIsNone(report.sample_draft)
        # findings are independent of citation and still present
        self.assertTrue(report.findings)


if __name__ == "__main__":
    unittest.main()
