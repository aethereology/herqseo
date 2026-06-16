from __future__ import annotations

import sys
import unittest
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from queryclear_agent_runtime import (  # noqa: E402
    ApprovalRequired,
    BrandVoice,
    InMemoryBudgetRepository,
    LoopError,
    LoopService,
    ModelResponse,
    PublishResult,
    TokenBudget,
    TokenMeter,
)

_HOME = "<html><head><title>Invoice Automation for SaaS</title></head><body><p>x</p></body></html>"


class _FakeFetcher:
    def fetch(self, url: str) -> str:
        return _HOME


class _FakeProvider:
    def __init__(self, *, cite: bool) -> None:
        self._cite = cite

    def complete(self, request, prompt, *, system=None) -> ModelResponse:
        if request.task_class == "classification":
            content = "best invoice automation for saas"  # one seeded prompt
        elif request.task_class == "monitoring":
            content = "Try QueryClear." if self._cite else "Use a competitor."
        else:
            content = "## Answer\nQueryClear automates invoices."
        return ModelResponse(content=content, input_tokens=40, output_tokens=80, cost_usd=Decimal("0.001"))


class _FakePublisher:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def publish(self, *, title, body, status="draft") -> PublishResult:
        self.calls.append({"status": status})
        return PublishResult(cms_post_id="900", url="https://staging.test/?p=900", status=status)


def _service(*, cite: bool) -> LoopService:
    repo = InMemoryBudgetRepository({"org_1": TokenBudget("org_1", 1_000_000)})
    return LoopService(
        meter=TokenMeter(repo),
        provider=_FakeProvider(cite=cite),
        fetcher=_FakeFetcher(),
        voice=BrandVoice("QueryClear", "Plain and direct."),
        publisher=_FakePublisher(),
    )


def _run(service: LoopService):
    return service.run(
        org_id="org_1", domain_id="domain_1",
        domain_url="https://example.com", brand="QueryClear", samples=2,
    )


class LoopServiceTest(unittest.TestCase):
    def test_run_produces_opportunity_and_draft(self) -> None:
        service = _service(cite=False)
        summary = _run(service)

        self.assertEqual(len(summary.opportunities), 1)
        self.assertIsNotNone(summary.draft)
        self.assertEqual(summary.draft.status, "pending_approval")
        # draft is retrievable by id
        self.assertEqual(
            service.get_draft(summary.draft.id, org_id="org_1").id, summary.draft.id
        )

    def test_run_without_gap_makes_no_draft(self) -> None:
        summary = _run(_service(cite=True))
        self.assertEqual(summary.opportunities, ())
        self.assertIsNone(summary.draft)

    def test_publish_requires_approval(self) -> None:
        service = _service(cite=False)
        summary = _run(service)

        with self.assertRaises(ApprovalRequired):
            service.publish(summary.draft.id, org_id="org_1", actor="founder@x.com")

    def test_approve_then_publish_drafts_and_audits(self) -> None:
        service = _service(cite=False)
        summary = _run(service)

        service.review(
            summary.draft.id, org_id="org_1", approved=True, reviewer="founder@x.com"
        )
        outcome = service.publish(summary.draft.id, org_id="org_1", actor="founder@x.com")

        self.assertEqual(outcome.piece.status, "published")
        self.assertEqual(outcome.result.status, "draft")  # staging only
        self.assertEqual(len(service.audit_events.list(org_id="org_1")), 1)
        # stored draft reflects published state
        self.assertEqual(
            service.get_draft(summary.draft.id, org_id="org_1").status, "published"
        )

    def test_unknown_draft_raises(self) -> None:
        with self.assertRaises(LoopError):
            _service(cite=False).get_draft("nope", org_id="org_1")

    def test_run_uses_per_domain_brand_voice(self) -> None:
        class _CapturingProvider(_FakeProvider):
            def __init__(self) -> None:
                super().__init__(cite=False)
                self.systems: list[str] = []

            def complete(self, request, prompt, *, system=None):
                if request.task_class == "content_generation":
                    self.systems.append(system or "")
                return super().complete(request, prompt, system=system)

        service = _service(cite=False)
        provider = _CapturingProvider()
        service.provider = provider
        service.run(
            org_id="org_1", domain_id="domain_1",
            domain_url="https://example.com", brand="Globex",
            brand_voice="Wry and concise.", samples=2,
        )

        self.assertTrue(provider.systems)
        system = provider.systems[0]
        self.assertIn("Globex", system)  # requested brand, not the default voice's
        self.assertIn("Wry and concise.", system)

    def test_run_derives_voice_from_site_when_none_provided(self) -> None:
        # A content-rich site so the voice corpus clears the threshold.
        rich = "We automate accounts payable for finance teams. Plain words, fast results. " * 5

        class _RichFetcher:
            def fetch(self, url: str) -> str:
                return f"<html><head><title>Acme AP</title></head><body><p>{rich}</p></body></html>"

        class _VoiceAwareProvider:
            def __init__(self) -> None:
                self.content_systems: list[str] = []

            def complete(self, request, prompt, *, system=None) -> ModelResponse:
                if request.task_class == "classification" and "style guide" in prompt.lower():
                    content = "Crisp, concrete, finance-savvy; no buzzwords."  # derived voice
                elif request.task_class == "classification":
                    content = "best ap automation"  # prompt seeding
                elif request.task_class == "monitoring":
                    content = "Use a competitor."  # gap
                else:
                    self.content_systems.append(system or "")
                    content = "## Answer\nAcme automates AP."
                return ModelResponse(content=content, input_tokens=30, output_tokens=60, cost_usd=Decimal("0.001"))

        repo = InMemoryBudgetRepository({"org_1": TokenBudget("org_1", 1_000_000)})
        provider = _VoiceAwareProvider()
        service = LoopService(
            meter=TokenMeter(repo), provider=provider, fetcher=_RichFetcher(),
            voice=BrandVoice("QueryClear", "Plain and direct."), publisher=_FakePublisher(),
        )
        service.run(
            org_id="org_1", domain_id="domain_1",
            domain_url="https://acme.test", brand="Acme", samples=2,
        )

        self.assertTrue(provider.content_systems)
        # the voice derived from the site (not the service default) drives the draft
        self.assertIn("Crisp, concrete, finance-savvy", provider.content_systems[0])

    def test_run_falls_back_to_default_voice_guidelines(self) -> None:
        class _CapturingProvider(_FakeProvider):
            def __init__(self) -> None:
                super().__init__(cite=False)
                self.systems: list[str] = []

            def complete(self, request, prompt, *, system=None):
                if request.task_class == "content_generation":
                    self.systems.append(system or "")
                return super().complete(request, prompt, system=system)

        service = _service(cite=False)
        provider = _CapturingProvider()
        service.provider = provider
        service.run(
            org_id="org_1", domain_id="domain_1",
            domain_url="https://example.com", brand="QueryClear", samples=2,
        )

        self.assertIn("Plain and direct.", provider.systems[0])  # service default


if __name__ == "__main__":
    unittest.main()
