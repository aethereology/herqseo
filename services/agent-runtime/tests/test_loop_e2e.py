from __future__ import annotations

import sys
import unittest
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from queryclear_agent_runtime import (  # noqa: E402
    ApprovalRequired,
    AuditEvent,
    BrandVoice,
    InMemoryBudgetRepository,
    ModelResponse,
    PublishResult,
    TokenBudget,
    TokenMeter,
    crawl_site,
    generate_content_draft,
    publish_content,
    review_content,
    run_monitoring,
)

_HOME = """
<html><head><title>Invoice Automation for SaaS</title></head>
<body><h1>Automate invoices</h1><p>Finance tooling.</p></body></html>
"""


class _FakeFetcher:
    def fetch(self, url: str) -> str:
        return _HOME


class _FakeProvider:
    """Brand is invisible during monitoring (drives an opportunity); content
    generation returns a draft body."""

    def complete(self, request, prompt, *, system=None) -> ModelResponse:
        if request.task_class == "monitoring":
            content = "I'd recommend a competitor."
        else:
            content = "## Direct answer\nQueryClear automates invoicing for SaaS teams."
        return ModelResponse(content=content, input_tokens=50, output_tokens=120, cost_usd=Decimal("0.001"))


class _FakePublisher:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def publish(self, *, title, body, status="draft") -> PublishResult:
        self.calls.append({"title": title, "status": status})
        return PublishResult(cms_post_id="900", url="https://staging.test/?p=900", status=status)


class OperatorLoopEndToEndTest(unittest.TestCase):
    def test_crawl_to_published_draft_is_metered_and_audited(self) -> None:
        repo = InMemoryBudgetRepository({"org_1": TokenBudget("org_1", 1_000_000)})
        meter = TokenMeter(repo)
        provider = _FakeProvider()
        audit: list[AuditEvent] = []

        # 1. crawl one site
        snapshot = crawl_site(_FakeFetcher(), "https://example.com", ("/",))

        # 2. monitor -> opportunities (every model call metered)
        monitoring = run_monitoring(
            meter, provider, snapshot, brand="QueryClear",
            org_id="org_1", domain_id="domain_1", samples=2,
        )
        self.assertEqual(len(monitoring.opportunities), 1)
        top = monitoring.opportunities[0]

        # 3. generate ONE brand-voice draft (metered)
        piece = generate_content_draft(
            meter, provider, top, BrandVoice("QueryClear", "Plain and direct."),
            org_id="org_1", domain_id="domain_1",
        )
        self.assertEqual(piece.status, "pending_approval")

        # 4. Review-mode gate: unapproved draft cannot publish
        with self.assertRaises(ApprovalRequired):
            publish_content(_FakePublisher(), piece, autonomy_mode="review",
                            actor="founder@x.com", audit_log=audit)

        # 5. human approves -> publish to staging/draft
        approved = review_content(piece, approved=True, reviewer="founder@x.com")
        publisher = _FakePublisher()
        outcome = publish_content(
            publisher, approved, autonomy_mode="review",
            actor="founder@x.com", audit_log=audit,
        )

        # loop assertions: published to draft, audited, fully metered
        self.assertEqual(publisher.calls[0]["status"], "draft")  # never live
        self.assertEqual(outcome.piece.status, "published")
        self.assertEqual(outcome.piece.cms_post_id, "900")
        self.assertEqual(len(audit), 1)
        self.assertEqual(audit[0].metadata["usage_record_id"], piece.usage_record_id)

        # every model call was metered: 2 monitoring samples + 1 content draft
        self.assertEqual(len(repo.records), 3)
        self.assertGreater(repo.get_budget("org_1").used_tokens, 0)


if __name__ == "__main__":
    unittest.main()
