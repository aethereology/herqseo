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
    if check.measured:
        title = f"Improve {check.engine} visibility for: {check.query}"
        rationale = (
            f"On {check.engine}, '{check.brand}' was cited in "
            f"{check.cited_count}/{check.samples} sampled answers ({freq:.0%})."
        )
        action = (
            "Review the cited answers and publish accurate, answer-first coverage "
            "where the site does not yet satisfy this query."
        )
        evidence = f"{check.engine}:{check.query}"
    else:
        title = f"Review answer coverage for: {check.query}"
        rationale = (
            f"In a general-model scenario, '{check.brand}' appeared in "
            f"{check.cited_count}/{check.samples} generated answer samples ({freq:.0%}). "
            "This is a hypothesis, not a live engine measurement."
        )
        action = (
            "Review the site's existing coverage for this buyer question. If the business facts "
            "support it, add a direct answer with relevant first-party evidence."
        )
        evidence = f"modeled-scenario:{check.query}"
    return Recommendation(
        rank=0,
        priority=(1 if check.cited_count == 0 else 2) if check.measured else 3,
        kind="content",
        title=title,
        rationale=rationale,
        action=action,
        provenance="measured" if check.measured else "estimated",
        evidence=evidence,
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

    Modeled scenarios are low-priority review hypotheses. Verified technical
    issues take precedence over speculative model gaps. Sort by priority,
    measured evidence, then title for stability.
    """
    items = [_from_finding(f) for f in findings]
    items += [_from_check(c) for c in checks if c.citation_frequency < threshold]
    items.sort(key=lambda r: (r.priority, 0 if r.provenance == "measured" else 1, r.title))
    # Group equivalent actions without losing evidence from other fetched pages.
    # Different fixes or evidence classes must never be collapsed together.
    groups: dict[tuple[str, str, str, str], list[Recommendation]] = {}
    for rec in items:
        key = (rec.kind, rec.title, rec.provenance, rec.action)
        groups.setdefault(key, []).append(rec)
    deduped = [
        replace(
            group[0],
            rationale="\n".join(dict.fromkeys(rec.rationale for rec in group)),
            evidence="\n".join(dict.fromkeys(rec.evidence for rec in group)),
        )
        for group in groups.values()
    ]
    return [replace(rec, rank=i) for i, rec in enumerate(deduped[:limit], start=1)]
