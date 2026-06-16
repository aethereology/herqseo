from __future__ import annotations

import sys
import unittest
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from queryclear_agent_runtime import (  # noqa: E402
    ApprovalRequired,
    BrandVoice,
    ContentPiece,
    InMemoryBudgetRepository,
    ModelRoute,
    ModelRoutingPolicy,
    ModelResponse,
    Opportunity,
    Page,
    SiteSnapshot,
    TokenBudget,
    TokenMeter,
    assert_approved_for_publish,
    derive_brand_voice,
    generate_content_draft,
    review_content,
)


class _RecordingProvider:
    def __init__(self, body: str) -> None:
        self._body = body
        self.requests = []
        self.prompts: list[str] = []
        self.systems: list[str | None] = []

    def complete(self, request, prompt, *, system=None) -> ModelResponse:
        self.requests.append(request)
        self.prompts.append(prompt)
        self.systems.append(system)
        return ModelResponse(
            content=self._body,
            input_tokens=200,
            output_tokens=600,
            cost_usd=Decimal("0.0050"),
        )


def _opportunity(opp_type: str = "content") -> Opportunity:
    return Opportunity(
        id="opp-vp-0",
        opportunity_type=opp_type,
        title="Improve AI visibility for: best invoice automation for saas",
        rationale="Brand 'QueryClear' cited in 0/3 samples (0%); below the 50% target.",
        priority=1,
        prompt_id="vp-0",
    )


def _voice() -> BrandVoice:
    return BrandVoice(brand="QueryClear", guidelines="Plain, direct, founder-led. No hype.")


def _meter() -> tuple[TokenMeter, InMemoryBudgetRepository]:
    repo = InMemoryBudgetRepository({"org_1": TokenBudget("org_1", 1_000_000)})
    return TokenMeter(repo), repo


class GenerateContentDraftTest(unittest.TestCase):
    def test_generates_metered_draft_pending_approval(self) -> None:
        meter, repo = _meter()
        provider = _RecordingProvider("## Direct answer\nQueryClear automates invoices...")

        piece = generate_content_draft(
            meter, provider, _opportunity(), _voice(),
            org_id="org_1", domain_id="domain_1",
        )

        self.assertIsInstance(piece, ContentPiece)
        self.assertEqual(piece.status, "pending_approval")
        self.assertEqual(piece.opportunity_id, "opp-vp-0")
        self.assertIn("QueryClear automates invoices", piece.body)
        self.assertEqual(piece.cost_usd, Decimal("0.0050"))
        self.assertTrue(piece.usage_record_id)
        # metered as content generation
        self.assertEqual(len(repo.records), 1)
        self.assertEqual(repo.records[0].task_class, "content_generation")

    def test_conditions_on_brand_voice_and_opportunity(self) -> None:
        meter, _ = _meter()
        provider = _RecordingProvider("body")

        generate_content_draft(
            meter, provider, _opportunity(), _voice(),
            org_id="org_1", domain_id="domain_1",
        )

        self.assertIn("QueryClear", provider.systems[0])
        self.assertIn("invoice automation", provider.prompts[0].lower())

    def test_rejects_non_content_opportunity(self) -> None:
        meter, _ = _meter()
        provider = _RecordingProvider("body")
        with self.assertRaises(ValueError):
            generate_content_draft(
                meter, provider, _opportunity("technical"), _voice(),
                org_id="org_1", domain_id="domain_1",
            )

    def test_uses_routing_policy_for_content_generation(self) -> None:
        meter, _ = _meter()
        provider = _RecordingProvider("body")
        policy = ModelRoutingPolicy(
            {
                "content_generation": ModelRoute(
                    provider="anthropic", model="claude-sonnet-4-6"
                )
            }
        )

        piece = generate_content_draft(
            meter, provider, _opportunity(), _voice(),
            org_id="org_1", domain_id="domain_1", routing_policy=policy,
        )

        self.assertEqual(provider.requests[0].provider, "anthropic")
        self.assertEqual(provider.requests[0].model, "claude-sonnet-4-6")
        self.assertEqual(piece.model, "claude-sonnet-4-6")


def _rich_snapshot() -> SiteSnapshot:
    body = (
        "We help finance teams automate accounts payable. No fluff, no jargon — "
        "just clear steps that get invoices paid faster. " * 3
    )
    return SiteSnapshot(
        "https://acme.test",
        (Page(url="https://acme.test/", title="Acme — AP automation", headings=("Pay faster",), text=body),),
    )


class DeriveBrandVoiceTest(unittest.TestCase):
    def test_derives_guidelines_from_site_copy(self) -> None:
        meter, repo = _meter()
        provider = _RecordingProvider("Direct and plain-spoken; short sentences; avoid jargon.")

        voice = derive_brand_voice(
            meter, provider, _rich_snapshot(), "Acme", org_id="org_1", domain_id="domain_1"
        )

        self.assertEqual(voice.brand, "Acme")
        self.assertEqual(voice.guidelines, "Direct and plain-spoken; short sentences; avoid jargon.")
        # metered as a (cheap) analysis call, and the site copy was in the prompt
        self.assertEqual(len(repo.records), 1)
        self.assertEqual(repo.records[0].task_class, "classification")
        self.assertIn("accounts payable", provider.prompts[0].lower())

    def test_uses_routing_policy_for_voice_derivation(self) -> None:
        meter, _ = _meter()
        provider = _RecordingProvider("Direct and plain-spoken.")
        policy = ModelRoutingPolicy(
            {
                "classification": ModelRoute(
                    provider="anthropic", model="claude-haiku-4-5-20251001"
                )
            }
        )

        derive_brand_voice(
            meter, provider, _rich_snapshot(), "Acme",
            org_id="org_1", domain_id="domain_1", routing_policy=policy,
        )

        self.assertEqual(provider.requests[0].provider, "anthropic")
        self.assertEqual(provider.requests[0].model, "claude-haiku-4-5-20251001")

    def test_falls_back_when_site_too_thin(self) -> None:
        meter, repo = _meter()
        provider = _RecordingProvider("unused")
        thin = SiteSnapshot(
            "https://x.test", (Page(url="https://x.test/", title="Hi", headings=(), text="short"),)
        )

        voice = derive_brand_voice(
            meter, provider, thin, "X", org_id="org_1", domain_id="domain_1",
            fallback="House style.",
        )

        self.assertEqual(voice.guidelines, "House style.")
        self.assertEqual(len(repo.records), 0)  # no model call when there's no signal


class ReviewContentTest(unittest.TestCase):
    def _piece(self) -> ContentPiece:
        meter, _ = _meter()
        provider = _RecordingProvider("draft body")
        return generate_content_draft(
            meter, provider, _opportunity(), _voice(),
            org_id="org_1", domain_id="domain_1",
        )

    def test_approve_sets_reviewer(self) -> None:
        approved = review_content(self._piece(), approved=True, reviewer="founder@x.com")
        self.assertEqual(approved.status, "approved")
        self.assertEqual(approved.reviewer, "founder@x.com")

    def test_reject_records_note(self) -> None:
        rejected = review_content(
            self._piece(), approved=False, reviewer="founder@x.com", note="off voice"
        )
        self.assertEqual(rejected.status, "rejected")
        self.assertEqual(rejected.review_note, "off voice")


class ApprovalGateTest(unittest.TestCase):
    def _piece(self, status: str) -> ContentPiece:
        return ContentPiece(
            id="cp-1", org_id="org_1", domain_id="domain_1",
            opportunity_id="opp-vp-0", title="t", body="b",
            status=status, model="gpt-4.1", usage_record_id="u1", cost_usd=Decimal("0"),
        )

    def test_review_mode_blocks_unapproved(self) -> None:
        with self.assertRaises(ApprovalRequired):
            assert_approved_for_publish(self._piece("pending_approval"), "review")
        with self.assertRaises(ApprovalRequired):
            assert_approved_for_publish(self._piece("rejected"), "review")

    def test_review_mode_allows_approved(self) -> None:
        # should not raise
        assert_approved_for_publish(self._piece("approved"), "review")

    def test_non_review_mode_disabled_in_m0(self) -> None:
        with self.assertRaises(ApprovalRequired):
            assert_approved_for_publish(self._piece("approved"), "auto_publish")


if __name__ == "__main__":
    unittest.main()
