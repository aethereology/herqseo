from __future__ import annotations

from dataclasses import dataclass, field

from .content import (
    BrandVoice,
    ContentPiece,
    generate_content_draft,
    review_content,
)
from .crawl import PageFetcher, crawl_site
from .metering import TokenMeter
from .monitoring import Opportunity, run_monitoring
from .providers import ModelProvider
from .publishing import AuditEvent, CmsPublisher, PublishOutcome, publish_content


class LoopError(RuntimeError):
    pass


@dataclass(frozen=True)
class RunSummary:
    run_id: str
    domain_id: str
    opportunities: tuple[Opportunity, ...]
    draft: ContentPiece | None


@dataclass
class LoopService:
    """In-memory orchestration of the M0 operator loop, framework-free so it can
    be unit-tested offline and driven by any adapter (the FastAPI app in app.py).

    Holds draft state in memory for M0; DB persistence is a follow-up.
    """

    meter: TokenMeter
    provider: ModelProvider
    fetcher: PageFetcher
    voice: BrandVoice
    publisher: CmsPublisher | None = None
    autonomy_mode: str = "review"
    audit_log: list[AuditEvent] = field(default_factory=list)
    _drafts: dict[str, ContentPiece] = field(default_factory=dict)
    _runs: int = 0

    def run(
        self,
        *,
        org_id: str,
        domain_id: str,
        domain_url: str,
        brand: str,
        seed_paths: tuple[str, ...] = ("/",),
        samples: int = 3,
    ) -> RunSummary:
        snapshot = crawl_site(self.fetcher, domain_url, seed_paths)
        monitoring = run_monitoring(
            self.meter, self.provider, snapshot, brand,
            org_id=org_id, domain_id=domain_id, samples=samples,
        )
        draft: ContentPiece | None = None
        if monitoring.opportunities:
            draft = generate_content_draft(
                self.meter, self.provider, monitoring.opportunities[0], self.voice,
                org_id=org_id, domain_id=domain_id,
            )
            self._drafts[draft.id] = draft
        self._runs += 1
        return RunSummary(
            run_id=f"run-{self._runs}",
            domain_id=domain_id,
            opportunities=monitoring.opportunities,
            draft=draft,
        )

    def get_draft(self, draft_id: str) -> ContentPiece:
        try:
            return self._drafts[draft_id]
        except KeyError as exc:
            raise LoopError(f"unknown draft {draft_id!r}") from exc

    def review(
        self, draft_id: str, *, approved: bool, reviewer: str, note: str | None = None
    ) -> ContentPiece:
        reviewed = review_content(
            self.get_draft(draft_id), approved=approved, reviewer=reviewer, note=note
        )
        self._drafts[draft_id] = reviewed
        return reviewed

    def publish(self, draft_id: str, *, actor: str) -> PublishOutcome:
        if self.publisher is None:
            raise LoopError("no CMS publisher configured")
        outcome = publish_content(
            self.publisher, self.get_draft(draft_id),
            autonomy_mode=self.autonomy_mode, actor=actor, audit_log=self.audit_log,
        )
        self._drafts[draft_id] = outcome.piece
        return outcome
