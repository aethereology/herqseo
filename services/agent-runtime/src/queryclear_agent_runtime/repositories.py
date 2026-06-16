"""Tenant-scoped persistence seams for the operator loop's stateful entities.

`LoopService` depends on these Protocols, never on a concrete store — the
default is in-memory (tests, offline demo); `db.py` provides the SQL-backed
implementations wired in by `serve.py` when ``DATABASE_URL`` is set. This mirrors
the `BudgetRepository` pattern already used by the token meter.

Every method takes ``org_id`` so the access path is tenant-scoped from the first
commit; the SQL implementations also enforce it via row-level security.
"""
from __future__ import annotations

from typing import Protocol, Sequence

from .content import ContentPiece
from .credentials import WordPressCredentials
from .crawl import SiteSnapshot
from .monitoring import Opportunity, VisibilityCheck
from .publishing import AuditEvent


class CmsCredentialRepository(Protocol):
    def save_wordpress(
        self, credentials: WordPressCredentials, *, org_id: str, domain_id: str
    ) -> str: ...
    def get_wordpress(self, ref: str, *, org_id: str) -> WordPressCredentials | None: ...
    def get_wordpress_for_domain(
        self, *, org_id: str, domain_id: str
    ) -> WordPressCredentials | None: ...


class CrawlSnapshotRepository(Protocol):
    def save(self, snapshot: SiteSnapshot, *, org_id: str, domain_id: str) -> str: ...
    def latest(self, *, org_id: str, domain_id: str) -> SiteSnapshot | None: ...


class VisibilityCheckRepository(Protocol):
    def save_all(
        self, checks: Sequence[VisibilityCheck], *, org_id: str, domain_id: str
    ) -> None: ...


class DraftRepository(Protocol):
    def save(self, piece: ContentPiece) -> None: ...
    def get(self, draft_id: str, *, org_id: str) -> ContentPiece | None: ...


class OpportunityRepository(Protocol):
    def save_all(
        self, opportunities: Sequence[Opportunity], *, org_id: str, domain_id: str
    ) -> None: ...


class AuditEventRepository(Protocol):
    def append(self, event: AuditEvent, *, org_id: str, domain_id: str) -> None: ...
    def list(self, *, org_id: str) -> list[AuditEvent]: ...


class VoiceProfileRepository(Protocol):
    def get(self, *, org_id: str, domain_id: str) -> str | None: ...
    def save(self, *, org_id: str, domain_id: str, brand: str, guidelines: str) -> None: ...


class InMemoryCrawlSnapshotRepository:
    def __init__(self) -> None:
        self._snapshots: dict[tuple[str, str], list[tuple[str, SiteSnapshot]]] = {}
        self._next = 0

    def save(self, snapshot: SiteSnapshot, *, org_id: str, domain_id: str) -> str:
        self._next += 1
        snapshot_id = f"crawl-{self._next}"
        self._snapshots.setdefault((org_id, domain_id), []).append((snapshot_id, snapshot))
        return snapshot_id

    def latest(self, *, org_id: str, domain_id: str) -> SiteSnapshot | None:
        snapshots = self._snapshots.get((org_id, domain_id), [])
        return snapshots[-1][1] if snapshots else None


class InMemoryCmsCredentialRepository:
    def __init__(self) -> None:
        self._by_ref: dict[str, tuple[str, str, WordPressCredentials]] = {}
        self._next = 0

    def save_wordpress(
        self, credentials: WordPressCredentials, *, org_id: str, domain_id: str
    ) -> str:
        self._next += 1
        ref = f"cmscred-{self._next}"
        self._by_ref[ref] = (org_id, domain_id, credentials)
        return ref

    def get_wordpress(self, ref: str, *, org_id: str) -> WordPressCredentials | None:
        saved = self._by_ref.get(ref)
        if saved is None:
            return None
        owner, _domain_id, credentials = saved
        return credentials if owner == org_id else None

    def get_wordpress_for_domain(
        self, *, org_id: str, domain_id: str
    ) -> WordPressCredentials | None:
        for owner, saved_domain_id, credentials in self._by_ref.values():
            if owner == org_id and saved_domain_id == domain_id:
                return credentials
        return None


class InMemoryVisibilityCheckRepository:
    def __init__(self) -> None:
        self.saved: list[VisibilityCheck] = []

    def save_all(
        self, checks: Sequence[VisibilityCheck], *, org_id: str, domain_id: str
    ) -> None:
        self.saved.extend(checks)


class InMemoryDraftRepository:
    def __init__(self) -> None:
        self._by_id: dict[str, ContentPiece] = {}

    def save(self, piece: ContentPiece) -> None:
        self._by_id[piece.id] = piece

    def get(self, draft_id: str, *, org_id: str) -> ContentPiece | None:
        piece = self._by_id.get(draft_id)
        if piece is None or piece.org_id != org_id:
            return None
        return piece


class InMemoryOpportunityRepository:
    def __init__(self) -> None:
        self.saved: list[Opportunity] = []

    def save_all(
        self, opportunities: Sequence[Opportunity], *, org_id: str, domain_id: str
    ) -> None:
        self.saved.extend(opportunities)


class InMemoryAuditEventRepository:
    def __init__(self) -> None:
        self._events: list[tuple[str, AuditEvent]] = []

    def append(self, event: AuditEvent, *, org_id: str, domain_id: str) -> None:
        self._events.append((org_id, event))

    def list(self, *, org_id: str) -> list[AuditEvent]:
        return [event for owner, event in self._events if owner == org_id]


class InMemoryVoiceProfileRepository:
    def __init__(self) -> None:
        self._by_domain: dict[tuple[str, str], str] = {}

    def get(self, *, org_id: str, domain_id: str) -> str | None:
        return self._by_domain.get((org_id, domain_id))

    def save(self, *, org_id: str, domain_id: str, brand: str, guidelines: str) -> None:
        self._by_domain[(org_id, domain_id)] = guidelines
