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
    ModelResponse,
    Opportunity,
    TokenBudget,
    TokenMeter,
    assert_approved_for_publish,
    generate_content_draft,
    review_content,
)


class _RecordingProvider:
    def __init__(self, body: str) -> None:
        self._body = body
        self.prompts: list[str] = []
        self.systems: list[str | None] = []

    def complete(self, request, prompt, *, system=None) -> ModelResponse:
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
