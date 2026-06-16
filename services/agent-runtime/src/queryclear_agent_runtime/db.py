"""SQLAlchemy-backed persistence for the money path (model usage + token budget).

Imports SQLAlchemy, so this module is NOT imported by the package ``__init__`` —
load it directly (``from queryclear_agent_runtime.db import ...``) and install the
``db`` extra. Columns mirror packages/db (the migration is the source of truth);
types are kept portable so the same code runs on Postgres and on SQLite (tests).
"""
from __future__ import annotations

from datetime import datetime
from uuid import uuid4

import sqlalchemy as sa

from .content import ContentPiece
from .metering import BudgetExceeded, TokenBudget, UsageRecord
from .publishing import AuditEvent

metadata = sa.MetaData()

# Minimal projections of the real tables — only the columns this repo touches.
organizations = sa.Table(
    "organizations",
    metadata,
    sa.Column("id", sa.String, primary_key=True),
    sa.Column("token_budget_monthly", sa.Integer, nullable=False),
    sa.Column("token_used_current_period", sa.Integer, nullable=False, default=0),
)

model_usage = sa.Table(
    "model_usage",
    metadata,
    sa.Column("id", sa.String, primary_key=True),
    sa.Column("org_id", sa.String, nullable=False),
    sa.Column("domain_id", sa.String, nullable=False),
    sa.Column("task_class", sa.String, nullable=False),
    sa.Column("provider", sa.String, nullable=False),
    sa.Column("model", sa.String, nullable=False),
    sa.Column("input_tokens", sa.Integer, nullable=False),
    sa.Column("output_tokens", sa.Integer, nullable=False),
    sa.Column("cost_usd", sa.Numeric(12, 6), nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
)

opportunities = sa.Table(
    "opportunities",
    metadata,
    sa.Column("id", sa.String, primary_key=True),
    sa.Column("org_id", sa.String, nullable=False),
    sa.Column("domain_id", sa.String, nullable=False),
    sa.Column("type", sa.String, nullable=False),
    sa.Column("priority", sa.Integer, nullable=False),
    sa.Column("title", sa.String, nullable=False),
    sa.Column("rationale", sa.String, nullable=False),
    sa.Column("source_prompt", sa.String, nullable=True),
    sa.Column("status", sa.String, nullable=False),
)

content_pieces = sa.Table(
    "content_pieces",
    metadata,
    sa.Column("id", sa.String, primary_key=True),
    sa.Column("org_id", sa.String, nullable=False),
    sa.Column("domain_id", sa.String, nullable=False),
    sa.Column("opportunity_id", sa.String, nullable=True),
    sa.Column("title", sa.String, nullable=False),
    sa.Column("body", sa.String, nullable=True),
    sa.Column("status", sa.String, nullable=False),
    sa.Column("model", sa.String, nullable=True),
    sa.Column("usage_record_id", sa.String, nullable=True),
    sa.Column("cost_usd", sa.Numeric(12, 6), nullable=True),
    sa.Column("reviewer", sa.String, nullable=True),
    sa.Column("review_note", sa.String, nullable=True),
    sa.Column("cms_post_id", sa.String, nullable=True),
    sa.Column("published_at", sa.String, nullable=True),
)

audit_events = sa.Table(
    "audit_events",
    metadata,
    sa.Column("id", sa.String, primary_key=True),
    sa.Column("org_id", sa.String, nullable=False),
    sa.Column("domain_id", sa.String, nullable=False),
    sa.Column("entity_type", sa.String, nullable=False),
    sa.Column("entity_id", sa.String, nullable=False),
    sa.Column("action", sa.String, nullable=False),
    sa.Column("actor", sa.String, nullable=False),
    sa.Column("metadata", sa.JSON, nullable=False),
    sa.Column("created_at", sa.String, nullable=False),
)


def create_engine_from_url(url: str) -> sa.Engine:
    return sa.create_engine(url, future=True)


def _scope_conn(conn: sa.Connection, org_id: str) -> None:
    """Set the RLS org GUC on Postgres (no-op on SQLite)."""
    if conn.dialect.name == "postgresql":
        conn.execute(
            sa.text("SELECT set_config('app.current_org', :org, true)"),
            {"org": org_id},
        )


class SqlBudgetRepository:
    """Postgres/SQLite-backed `BudgetRepository`. Writes `model_usage` and keeps
    `organizations.token_used_current_period` in step, atomically per call.

    On Postgres it sets `app.current_org` so row-level security applies; queries
    are also scoped by `org_id` explicitly (defense in depth, per data-model.md).
    """

    def __init__(self, engine: sa.Engine) -> None:
        self._engine = engine

    def get_budget(self, org_id: str) -> TokenBudget:
        with self._engine.begin() as conn:
            self._scope(conn, org_id)
            row = conn.execute(
                sa.select(
                    organizations.c.token_budget_monthly,
                    organizations.c.token_used_current_period,
                ).where(organizations.c.id == org_id)
            ).first()
        if row is None:
            raise BudgetExceeded(f"No token budget configured for org {org_id}")
        return TokenBudget(org_id=org_id, monthly_tokens=row[0], used_tokens=row[1])

    def add_usage(self, record: UsageRecord) -> TokenBudget:
        total = record.input_tokens + record.output_tokens
        with self._engine.begin() as conn:
            self._scope(conn, record.org_id)
            conn.execute(
                sa.insert(model_usage).values(
                    id=record.id,
                    org_id=record.org_id,
                    domain_id=record.domain_id,
                    task_class=record.task_class,
                    provider=record.provider,
                    model=record.model,
                    input_tokens=record.input_tokens,
                    output_tokens=record.output_tokens,
                    cost_usd=record.cost_usd,
                    created_at=record.created_at,
                )
            )
            conn.execute(
                sa.update(organizations)
                .where(organizations.c.id == record.org_id)
                .values(
                    token_used_current_period=organizations.c.token_used_current_period
                    + total
                )
            )
            row = conn.execute(
                sa.select(
                    organizations.c.token_budget_monthly,
                    organizations.c.token_used_current_period,
                ).where(organizations.c.id == record.org_id)
            ).first()
        return TokenBudget(
            org_id=record.org_id, monthly_tokens=row[0], used_tokens=row[1]
        )

    def _scope(self, conn: sa.Connection, org_id: str) -> None:
        if conn.dialect.name == "postgresql":
            conn.execute(
                sa.text("SELECT set_config('app.current_org', :org, true)"),
                {"org": org_id},
            )


def _iso(value: object) -> str | None:
    """Normalize a timestamp column to the runtime's ISO-string form. SQLite
    returns the stored string; Postgres returns a datetime."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


class SqlDraftRepository:
    """Postgres/SQLite-backed `DraftRepository`. Upserts the draft so the same
    piece can be saved through its lifecycle (created -> reviewed -> published)."""

    def __init__(self, engine: sa.Engine) -> None:
        self._engine = engine

    def save(self, piece: ContentPiece) -> None:
        values = {
            "id": piece.id,
            "org_id": piece.org_id,
            "domain_id": piece.domain_id,
            "opportunity_id": piece.opportunity_id,
            "title": piece.title,
            "body": piece.body,
            "status": piece.status,
            "model": piece.model,
            "usage_record_id": piece.usage_record_id,
            "cost_usd": piece.cost_usd,
            "reviewer": piece.reviewer,
            "review_note": piece.review_note,
            "cms_post_id": piece.cms_post_id,
            "published_at": piece.published_at,
        }
        with self._engine.begin() as conn:
            _scope_conn(conn, piece.org_id)
            updated = conn.execute(
                sa.update(content_pieces)
                .where(
                    content_pieces.c.id == piece.id,
                    content_pieces.c.org_id == piece.org_id,
                )
                .values(values)
            )
            if updated.rowcount == 0:
                conn.execute(sa.insert(content_pieces).values(values))

    def get(self, draft_id: str, *, org_id: str) -> ContentPiece | None:
        with self._engine.begin() as conn:
            _scope_conn(conn, org_id)
            row = conn.execute(
                sa.select(content_pieces).where(
                    content_pieces.c.id == draft_id,
                    content_pieces.c.org_id == org_id,
                )
            ).mappings().first()
        if row is None:
            return None
        return ContentPiece(
            id=row["id"],
            org_id=row["org_id"],
            domain_id=row["domain_id"],
            opportunity_id=row["opportunity_id"],
            title=row["title"],
            body=row["body"],
            status=row["status"],
            model=row["model"],
            usage_record_id=row["usage_record_id"],
            cost_usd=row["cost_usd"],
            reviewer=row["reviewer"],
            review_note=row["review_note"],
            cms_post_id=row["cms_post_id"],
            published_at=_iso(row["published_at"]),
        )


class SqlOpportunityRepository:
    """Postgres/SQLite-backed `OpportunityRepository`. Persists proposed
    opportunities so a draft's `opportunity_id` FK resolves and reruns don't
    silently lose them."""

    def __init__(self, engine: sa.Engine) -> None:
        self._engine = engine

    def save_all(self, items, *, org_id: str, domain_id: str) -> None:  # type: ignore[no-untyped-def]
        rows = [
            {
                "id": opp.id,
                "org_id": org_id,
                "domain_id": domain_id,
                "type": opp.opportunity_type,
                "priority": opp.priority,
                "title": opp.title,
                "rationale": opp.rationale,
                "source_prompt": opp.prompt_id,
                "status": opp.status,
            }
            for opp in items
        ]
        if not rows:
            return
        with self._engine.begin() as conn:
            _scope_conn(conn, org_id)
            conn.execute(sa.insert(opportunities), rows)


class SqlAuditEventRepository:
    """Postgres/SQLite-backed `AuditEventRepository` for the operator action log."""

    def __init__(self, engine: sa.Engine) -> None:
        self._engine = engine

    def append(self, event: AuditEvent, *, org_id: str, domain_id: str) -> None:
        with self._engine.begin() as conn:
            _scope_conn(conn, org_id)
            conn.execute(
                sa.insert(audit_events).values(
                    id=str(uuid4()),
                    org_id=org_id,
                    domain_id=domain_id,
                    entity_type=event.entity_type,
                    entity_id=event.entity_id,
                    action=event.action,
                    actor=event.actor,
                    metadata=event.metadata,
                    created_at=event.created_at,
                )
            )

    def list(self, *, org_id: str) -> list[AuditEvent]:
        with self._engine.begin() as conn:
            _scope_conn(conn, org_id)
            rows = conn.execute(
                sa.select(audit_events)
                .where(audit_events.c.org_id == org_id)
                .order_by(audit_events.c.created_at)
            ).mappings().all()
        return [
            AuditEvent(
                entity_type=row["entity_type"],
                entity_id=row["entity_id"],
                action=row["action"],
                actor=row["actor"],
                created_at=_iso(row["created_at"]) or "",
                metadata=dict(row["metadata"] or {}),
            )
            for row in rows
        ]
