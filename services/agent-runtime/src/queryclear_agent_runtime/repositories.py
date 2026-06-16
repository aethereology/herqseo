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
from .monitoring import Opportunity
from .publishing import AuditEvent


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
