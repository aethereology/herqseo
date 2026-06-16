from __future__ import annotations

from dataclasses import dataclass

from .content import ContentPiece
from .monitoring import Opportunity, VisibilityCheck
from .recommendations import Recommendation
from .technical import Finding


@dataclass(frozen=True)
class AuditReport:
    """The read-only, client-facing audit: what's broken on-page, where the brand
    is invisible in AI answers, a prioritized action list, and a sample fix.
    No publish, no approval."""

    domain_url: str
    page_title: str
    findings: tuple[Finding, ...]
    checks: tuple[VisibilityCheck, ...]
    opportunities: tuple[Opportunity, ...]
    sample_draft: ContentPiece | None
    recommendations: tuple[Recommendation, ...] = ()
    # Brand voice detected from the prospect's own site (when a sample was drafted).
    detected_voice: str | None = None
