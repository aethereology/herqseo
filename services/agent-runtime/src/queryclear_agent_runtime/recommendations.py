"""Prioritized, explainable recommendations for the audit deliverable (P1-5).

A pure synthesis over signal we already collect: deterministic technical
findings (measured) and AI-visibility gaps (estimated until real engine adapters
land — see monitoring.py). Each recommendation carries its provenance so the
audit never presents an estimate as a measured fact.
"""
from __future__ import annotations

from dataclasses import dataclass, replace

from .monitoring import VisibilityCheck
from .technical import Finding

_SEVERITY_PRIORITY = {"high": 1, "medium": 2, "low": 3}


@dataclass(frozen=True)
class Recommendation:
    rank: int  # 1 = do first (sequential across the whole list)
    priority: int  # 1 high · 2 medium · 3 low — the bucket the rank derives from
    kind: str  # technical | content
    title: str
    rationale: str  # why it matters
    action: str  # what to do about it
    provenance: str  # measured | estimated
    evidence: str  # trace back to the source signal


def _from_finding(finding: Finding) -> Recommendation:
    return Recommendation(
        rank=0,
        priority=_SEVERITY_PRIORITY.get(finding.severity, 3),
        kind="technical",
        title=finding.title,
        rationale=finding.detail,
        action=finding.recommendation,
        provenance="measured",
        evidence=f"technical:{finding.code}" + (f" ({finding.url})" if finding.url else ""),
    )


def _from_check(check: VisibilityCheck) -> Recommendation:
    freq = check.citation_frequency
    return Recommendation(
        rank=0,
        priority=1 if check.cited_count == 0 else 2,
        kind="content",
        title=f"Win AI visibility for: {check.query}",
        rationale=(
            f"On {check.engine}, '{check.brand}' was cited in "
            f"{check.cited_count}/{check.samples} sampled answers ({freq:.0%})."
        ),
        action=(
            "Publish answer-first content targeting this query so AI engines "
            "can find and cite you for it."
        ),
        provenance="measured" if check.measured else "estimated",
        evidence=f"{check.engine}:{check.query}",
    )


def build_recommendations(
    findings: list[Finding],
    checks: list[VisibilityCheck],
    *,
    limit: int = 10,
    threshold: float = 0.5,
) -> list[Recommendation]:
    """Merge technical findings and below-threshold visibility gaps into one
    ranked, explainable action list, capped at `limit`.

    Sort order: priority bucket, then measured before estimated at the same
    bucket (a deterministic on-page fact beats an estimated visibility gap),
    then title for stability.
    """
    items = [_from_finding(f) for f in findings]
    items += [_from_check(c) for c in checks if c.citation_frequency < threshold]
    items.sort(key=lambda r: (r.priority, 0 if r.provenance == "measured" else 1, r.title))
    return [replace(rec, rank=i) for i, rec in enumerate(items[:limit], start=1)]
