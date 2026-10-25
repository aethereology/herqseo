from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from queryclear_agent_runtime import (  # noqa: E402
    Finding,
    Recommendation,
    VisibilityCheck,
    build_recommendations,
)


def _finding(code: str, severity: str) -> Finding:
    return Finding(
        code=code,
        severity=severity,
        title=f"{code} title",
        detail=f"{code} detail",
        recommendation=f"fix {code}",
        url="https://example.com/",
    )


def _check(query: str, cited: int, samples: int, *, measured: bool = False) -> VisibilityCheck:
    return VisibilityCheck(
        prompt_id=f"vp-{query}",
        query=query,
        brand="QueryClear",
        samples=samples,
        cited_count=cited,
        raw_responses=(),
        usage_record_ids=(),
        engine="chatgpt",
        measured=measured,
    )


class BuildRecommendationsTest(unittest.TestCase):
    def test_technical_findings_become_measured_recs_ranked_by_severity(self) -> None:
        recs = build_recommendations(
            [_finding("low_thing", "low"), _finding("high_thing", "high")],
            [],
        )

        self.assertEqual([r.title for r in recs], ["high_thing title", "low_thing title"])
        self.assertTrue(all(isinstance(r, Recommendation) for r in recs))
        self.assertTrue(all(r.kind == "technical" for r in recs))
        self.assertTrue(all(r.provenance == "measured" for r in recs))
        self.assertEqual([r.rank for r in recs], [1, 2])

    def test_visibility_gap_becomes_estimated_content_rec(self) -> None:
        recs = build_recommendations([], [_check("best invoice tool", 0, 3)], threshold=0.5)

        self.assertEqual(len(recs), 1)
        self.assertEqual(recs[0].kind, "content")
        self.assertEqual(recs[0].provenance, "estimated")
        self.assertIn("best invoice tool", recs[0].title)
        self.assertEqual(recs[0].evidence, "modeled-scenario:best invoice tool")
        self.assertIn("not a live engine measurement", recs[0].rationale)
        self.assertNotIn("chatgpt", recs[0].rationale.lower())

    def test_single_modeled_absence_does_not_outrank_verified_issues(self) -> None:
        recs = build_recommendations(
            [_finding("missing_schema", "medium"), _finding("metadata", "low")],
            [_check("buyer question", 0, 1)],
        )
        self.assertEqual([r.kind for r in recs], ["technical", "technical", "content"])
        self.assertEqual(recs[-1].priority, 3)

    def test_strong_visibility_is_not_a_recommendation(self) -> None:
        recs = build_recommendations([], [_check("we are cited", 3, 3)], threshold=0.5)
        self.assertEqual(recs, [])

    def test_zero_citation_outranks_partial_citation(self) -> None:
        recs = build_recommendations(
            [],
            [_check("partial", 1, 4, measured=True), _check("zero", 0, 4, measured=True)],
            threshold=0.9,
        )
        self.assertEqual(recs[0].title, "Improve chatgpt visibility for: zero")

    def test_measured_technical_outranks_estimated_content_at_same_priority(self) -> None:
        # high-severity technical and a zero-citation gap are both priority 1;
        # the measured (deterministic) finding must come first.
        recs = build_recommendations(
            [_finding("high_thing", "high")],
            [_check("invisible", 0, 3)],
        )
        self.assertEqual(recs[0].kind, "technical")
        self.assertEqual(recs[1].kind, "content")

    def test_measured_check_keeps_measured_provenance(self) -> None:
        recs = build_recommendations([], [_check("real gap", 0, 3, measured=True)])
        self.assertEqual(recs[0].provenance, "measured")
        self.assertIn("chatgpt", recs[0].rationale)

    def test_dedupes_content_recs_by_query_across_engines(self) -> None:
        # The same buyer-intent query probed on two engines is ONE action
        # ("publish content for this query"), not two recommendations.
        recs = build_recommendations(
            [],
            [
                _check("best invoice tool", 0, 3),  # engine chatgpt
                VisibilityCheck(
                    prompt_id="vp-x", query="best invoice tool", brand="QueryClear",
                    samples=3, cited_count=0, raw_responses=(), usage_record_ids=(),
                    engine="gemini", measured=False,
                ),
            ],
        )
        self.assertEqual(len(recs), 1)
        self.assertIn("best invoice tool", recs[0].title)

    def test_limit_caps_and_reranks(self) -> None:
        findings = [_finding(f"f{i}", "medium") for i in range(12)]
        recs = build_recommendations(findings, [], limit=10)
        self.assertEqual(len(recs), 10)
        self.assertEqual([r.rank for r in recs], list(range(1, 11)))


if __name__ == "__main__":
    unittest.main()
