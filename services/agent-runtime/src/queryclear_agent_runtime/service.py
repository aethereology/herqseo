from __future__ import annotations

from dataclasses import dataclass, field

from .audit import AuditReport
from .content import (
    BrandVoice,
    ContentPiece,
    derive_brand_voice,
    generate_content_draft,
    review_content,
)
from .crawl import PageFetcher, check_site_resources, crawl_site
from .metering import TokenMeter
from .monitoring import Opportunity, run_monitoring
from .providers import ModelProvider
from .publishing import CmsPublisher, PublishOutcome, publish_content
from .repositories import (
    AuditEventRepository,
    DraftRepository,
    InMemoryAuditEventRepository,
    InMemoryDraftRepository,
    InMemoryOpportunityRepository,
    InMemoryVoiceProfileRepository,
    OpportunityRepository,
    VoiceProfileRepository,
)
from .technical import audit_site_resources, audit_snapshot


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
    drafts: DraftRepository = field(default_factory=InMemoryDraftRepository)
    opportunities: OpportunityRepository = field(
        default_factory=InMemoryOpportunityRepository
    )
    audit_events: AuditEventRepository = field(
        default_factory=InMemoryAuditEventRepository
    )
    voice_profiles: VoiceProfileRepository = field(
        default_factory=InMemoryVoiceProfileRepository
    )
    _runs: int = 0

    def _resolve_voice(
        self, brand: str, guidelines: str | None, snapshot, *, org_id: str, domain_id: str
    ) -> BrandVoice:
        """Resolve the brand voice for a customer run. Precedence: an explicit
        per-domain ``guidelines`` string > a previously cached derived profile >
        derive from the crawled site now (and cache it for next time). Caching
        avoids re-paying for derivation on every run."""
        resolved_brand = brand or self.voice.brand
        if guidelines:
            return BrandVoice(brand=resolved_brand, guidelines=guidelines)

        cached = self.voice_profiles.get(org_id=org_id, domain_id=domain_id)
        if cached:
            return BrandVoice(brand=resolved_brand, guidelines=cached)

        voice = derive_brand_voice(
            self.meter, self.provider, snapshot, resolved_brand,
            org_id=org_id, domain_id=domain_id, fallback=self.voice.guidelines,
        )
        self.voice_profiles.save(
            org_id=org_id, domain_id=domain_id,
            brand=voice.brand, guidelines=voice.guidelines,
        )
        return voice

    def run(
        self,
        *,
        org_id: str,
        domain_id: str,
        domain_url: str,
        brand: str,
        brand_voice: str | None = None,
        seed_paths: tuple[str, ...] = ("/",),
        samples: int = 3,
    ) -> RunSummary:
        snapshot = crawl_site(self.fetcher, domain_url, seed_paths)
        monitoring = run_monitoring(
            self.meter, self.provider, snapshot, brand,
            org_id=org_id, domain_id=domain_id, samples=samples,
        )
        self.opportunities.save_all(
            monitoring.opportunities, org_id=org_id, domain_id=domain_id
        )
        draft: ContentPiece | None = None
        if monitoring.opportunities:
            voice = self._resolve_voice(
                brand, brand_voice, snapshot, org_id=org_id, domain_id=domain_id
            )
            draft = generate_content_draft(
                self.meter, self.provider, monitoring.opportunities[0], voice,
                org_id=org_id, domain_id=domain_id,
            )
            self.drafts.save(draft)
        self._runs += 1
        return RunSummary(
            run_id=f"run-{self._runs}",
            domain_id=domain_id,
            opportunities=monitoring.opportunities,
            draft=draft,
        )

    def audit(
        self,
        domain_url: str,
        brand: str,
        *,
        org_id: str,
        domain_id: str,
        samples: int = 3,
        max_prompts: int = 5,
        seed_paths: tuple[str, ...] = ("/",),
    ) -> AuditReport:
        """Read-only audit: crawl → technical findings + invisible-query check +
        one sample draft. No state stored, no publish — the sales deliverable."""
        snapshot = crawl_site(self.fetcher, domain_url, seed_paths)
        findings = audit_snapshot(snapshot)
        findings.extend(
            audit_site_resources(check_site_resources(self.fetcher, domain_url), domain_url)
        )
        monitoring = run_monitoring(
            self.meter, self.provider, snapshot, brand,
            org_id=org_id, domain_id=domain_id, samples=samples, max_prompts=max_prompts,
        )
        sample: ContentPiece | None = None
        if monitoring.opportunities:
            # An audit analyzes the prospect's OWN site, so derive the voice fresh
            # from the crawl — never the operator's configured voice, and never
            # cached (the audited URL isn't this tenant's domain).
            voice = derive_brand_voice(
                self.meter, self.provider, snapshot, brand,
                org_id=org_id, domain_id=domain_id, fallback=self.voice.guidelines,
            )
            sample = generate_content_draft(
                self.meter, self.provider, monitoring.opportunities[0], voice,
                org_id=org_id, domain_id=domain_id,
            )
        return AuditReport(
            domain_url=domain_url,
            page_title=snapshot.pages[0].title if snapshot.pages else "",
            findings=tuple(findings),
            checks=monitoring.checks,
            opportunities=monitoring.opportunities,
            sample_draft=sample,
        )

    def get_draft(self, draft_id: str, *, org_id: str) -> ContentPiece:
        piece = self.drafts.get(draft_id, org_id=org_id)
        if piece is None:
            raise LoopError(f"unknown draft {draft_id!r}")
        return piece

    def review(
        self,
        draft_id: str,
        *,
        org_id: str,
        approved: bool,
        reviewer: str,
        note: str | None = None,
    ) -> ContentPiece:
        reviewed = review_content(
            self.get_draft(draft_id, org_id=org_id),
            approved=approved, reviewer=reviewer, note=note,
        )
        self.drafts.save(reviewed)
        return reviewed

    def publish(self, draft_id: str, *, org_id: str, actor: str) -> PublishOutcome:
        if self.publisher is None:
            raise LoopError("no CMS publisher configured")
        piece = self.get_draft(draft_id, org_id=org_id)
        outcome = publish_content(
            self.publisher, piece,
            autonomy_mode=self.autonomy_mode, actor=actor, audit_log=[],
        )
        self.audit_events.append(
            outcome.event, org_id=piece.org_id, domain_id=piece.domain_id
        )
        self.drafts.save(outcome.piece)
        return outcome
