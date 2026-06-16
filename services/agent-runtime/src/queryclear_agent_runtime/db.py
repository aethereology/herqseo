"""SQLAlchemy-backed persistence for the money path (model usage + token budget).

Imports SQLAlchemy, so this module is NOT imported by the package ``__init__`` —
load it directly (``from queryclear_agent_runtime.db import ...``) and install the
``db`` extra. Columns mirror packages/db (the migration is the source of truth);
types are kept portable so the same code runs on Postgres and on SQLite (tests).
"""
from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Sequence
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from .content import ContentPiece
from .credentials import SecretCipher, WordPressCredentials
from .crawl import Page, SiteSnapshot
from .metering import BudgetExceeded, TokenBudget, UsageRecord
from .monitoring import VisibilityCheck
from .publishing import AuditEvent

metadata = sa.MetaData()

# The real Postgres columns are `uuid`; SQLite (tests) has no uuid type. This
# variant binds/returns plain strings as native UUID on Postgres (so `uuid = $1`
# resolves) while staying a plain VARCHAR on SQLite (so fake ids like "cp-1"
# round-trip in offline tests).
_UUID = sa.String().with_variant(postgresql.UUID(as_uuid=False), "postgresql")


def _pg_enum(name: str, *values: str) -> sa.String:
    """A column that's plain VARCHAR on SQLite but the existing named Postgres
    enum (so inserts cast text -> enum, which isn't implicit). ``create_type``
    is off: the migration owns the type."""
    return sa.String().with_variant(
        postgresql.ENUM(*values, name=name, create_type=False), "postgresql"
    )


# The runtime carries timestamps as ISO strings; the Postgres columns are
# timestamptz. This variant casts the text on Postgres and stays a plain string
# on SQLite; `_iso()` normalizes reads on either backend.
_TS = sa.String().with_variant(postgresql.TIMESTAMP(timezone=True), "postgresql")


_OPP_TYPE = _pg_enum("OpportunityType", "content", "technical", "citation")
_OPP_STATUS = _pg_enum(
    "OpportunityStatus", "proposed", "approved", "rejected", "in_progress", "done"
)
_CONTENT_STATUS = _pg_enum(
    "ContentStatus", "draft", "pending_approval", "approved", "rejected",
    "published", "failed",
)
_AI_ENGINE = _pg_enum(
    "AiEngine",
    "chatgpt",
    "google_ai_overviews",
    "google_ai_mode",
    "gemini",
    "perplexity",
    "claude",
    "copilot",
    "grok",
)
_INTEGRATION_KIND = _pg_enum(
    "IntegrationKind", "ga4", "gsc", "hubspot", "salesforce", "shopify", "wordpress", "webflow"
)
_INTEGRATION_STATUS = _pg_enum("IntegrationStatus", "connected", "disconnected", "error")
_DOMAIN_STATUS = _pg_enum("DomainStatus", "onboarding", "active", "paused")

# Minimal projections of the real tables — only the columns this repo touches.
organizations = sa.Table(
    "organizations",
    metadata,
    sa.Column("id", _UUID, primary_key=True),
    sa.Column("token_budget_monthly", sa.Integer, nullable=False),
    sa.Column("token_used_current_period", sa.Integer, nullable=False, default=0),
)

domains = sa.Table(
    "domains",
    metadata,
    sa.Column("id", _UUID, primary_key=True),
    sa.Column("org_id", _UUID, nullable=False),
    sa.Column("url", sa.String, nullable=False),
    sa.Column("cms_type", sa.String, nullable=False),
    sa.Column("cms_credentials_ref", sa.String, nullable=True),
    sa.Column("status", _DOMAIN_STATUS, nullable=False),
)

integrations = sa.Table(
    "integrations",
    metadata,
    sa.Column("id", _UUID, primary_key=True),
    sa.Column("org_id", _UUID, nullable=False),
    sa.Column("kind", _INTEGRATION_KIND, nullable=False),
    sa.Column("credentials_ref", sa.String, nullable=False),
    sa.Column("status", _INTEGRATION_STATUS, nullable=False),
    sa.Column("connected_at", _TS, nullable=True),
)

cms_credentials = sa.Table(
    "cms_credentials",
    metadata,
    sa.Column("id", _UUID, primary_key=True),
    sa.Column("org_id", _UUID, nullable=False),
    sa.Column("domain_id", _UUID, nullable=False),
    sa.Column("kind", _INTEGRATION_KIND, nullable=False),
    sa.Column("encrypted_payload", sa.String, nullable=False),
    sa.Column("created_at", _TS, nullable=False),
    sa.Column("updated_at", _TS, nullable=False),
)

model_usage = sa.Table(
    "model_usage",
    metadata,
    sa.Column("id", _UUID, primary_key=True),
    sa.Column("org_id", _UUID, nullable=False),
    sa.Column("domain_id", _UUID, nullable=False),
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
    sa.Column("id", _UUID, primary_key=True),
    sa.Column("org_id", _UUID, nullable=False),
    sa.Column("domain_id", _UUID, nullable=False),
    sa.Column("type", _OPP_TYPE, nullable=False),
    sa.Column("priority", sa.Integer, nullable=False),
    sa.Column("title", sa.String, nullable=False),
    sa.Column("rationale", sa.String, nullable=False),
    sa.Column("source_prompt", sa.String, nullable=True),
    sa.Column("source_engine", _AI_ENGINE, nullable=True),
    sa.Column("status", _OPP_STATUS, nullable=False),
)

content_pieces = sa.Table(
    "content_pieces",
    metadata,
    sa.Column("id", _UUID, primary_key=True),
    sa.Column("org_id", _UUID, nullable=False),
    sa.Column("domain_id", _UUID, nullable=False),
    sa.Column("opportunity_id", _UUID, nullable=True),
    sa.Column("title", sa.String, nullable=False),
    sa.Column("body", sa.String, nullable=True),
    sa.Column("status", _CONTENT_STATUS, nullable=False),
    sa.Column("model", sa.String, nullable=True),
    sa.Column("usage_record_id", _UUID, nullable=True),
    sa.Column("cost_usd", sa.Numeric(12, 6), nullable=True),
    sa.Column("reviewer", sa.String, nullable=True),
    sa.Column("review_note", sa.String, nullable=True),
    sa.Column("cms_post_id", sa.String, nullable=True),
    sa.Column("published_at", _TS, nullable=True),
)

audit_events = sa.Table(
    "audit_events",
    metadata,
    sa.Column("id", _UUID, primary_key=True),
    sa.Column("org_id", _UUID, nullable=False),
    sa.Column("domain_id", _UUID, nullable=False),
    sa.Column("entity_type", sa.String, nullable=False),
    sa.Column("entity_id", sa.String, nullable=False),
    sa.Column("action", sa.String, nullable=False),
    sa.Column("actor", sa.String, nullable=False),
    sa.Column("metadata", sa.JSON, nullable=False),
    sa.Column("created_at", _TS, nullable=False),
)


brand_voice_profiles = sa.Table(
    "brand_voice_profiles",
    metadata,
    sa.Column("id", _UUID, primary_key=True),
    sa.Column("org_id", _UUID, nullable=False),
    sa.Column("domain_id", _UUID, nullable=False, unique=True),
    sa.Column("brand", sa.String, nullable=False),
    sa.Column("guidelines", sa.String, nullable=False),
    sa.Column("source", sa.String, nullable=False),
    sa.Column("updated_at", _TS, nullable=False),
)


crawl_snapshots = sa.Table(
    "crawl_snapshots",
    metadata,
    sa.Column("id", _UUID, primary_key=True),
    sa.Column("org_id", _UUID, nullable=False),
    sa.Column("domain_id", _UUID, nullable=False),
    sa.Column("captured_at", _TS, nullable=False),
    sa.Column("page_count", sa.Integer, nullable=False),
    sa.Column("storage_ref", sa.String, nullable=False),
)


crawl_pages = sa.Table(
    "crawl_pages",
    metadata,
    sa.Column("id", _UUID, primary_key=True),
    sa.Column("org_id", _UUID, nullable=False),
    sa.Column("domain_id", _UUID, nullable=False),
    sa.Column("snapshot_id", _UUID, nullable=False),
    sa.Column("ordinal", sa.Integer, nullable=False),
    sa.Column("url", sa.String, nullable=False),
    sa.Column("title", sa.String, nullable=False),
    sa.Column("headings", sa.JSON, nullable=False),
    sa.Column("text", sa.String, nullable=False),
    sa.Column("meta_description", sa.String, nullable=False),
    sa.Column("has_structured_data", sa.Boolean, nullable=False),
    sa.Column("links", sa.JSON, nullable=False),
    sa.Column("captured_at", _TS, nullable=False),
)


visibility_checks = sa.Table(
    "visibility_checks",
    metadata,
    sa.Column("id", _UUID, primary_key=True),
    sa.Column("org_id", _UUID, nullable=False),
    sa.Column("domain_id", _UUID, nullable=False),
    sa.Column("engine", _AI_ENGINE, nullable=False),
    sa.Column("prompt", sa.String, nullable=False),
    sa.Column("captured_at", _TS, nullable=False),
    sa.Column("brand_cited", sa.Boolean, nullable=False),
    sa.Column("citation_rank", sa.Integer, nullable=True),
    sa.Column("sentiment", sa.String, nullable=True),
    sa.Column("share_of_voice", sa.Numeric(8, 4), nullable=True),
    sa.Column("raw_response_ref", sa.String, nullable=False),
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


class SqlCmsCredentialRepository:
    """Stores encrypted CMS credentials and links the active domain/integration.

    The table stores ciphertext only. The returned ref is intentionally opaque to
    callers; today it is `cms_credentials:<uuid>` so the runtime can resolve it.
    """

    def __init__(self, engine: sa.Engine, cipher: SecretCipher) -> None:
        self._engine = engine
        self._cipher = cipher

    def save_wordpress(
        self, credentials: WordPressCredentials, *, org_id: str, domain_id: str
    ) -> str:
        now = datetime.now(UTC).isoformat()
        encrypted = self._cipher.encrypt_wordpress(credentials)
        with self._engine.begin() as conn:
            _scope_conn(conn, org_id)
            existing = conn.execute(
                sa.select(cms_credentials.c.id).where(
                    cms_credentials.c.org_id == org_id,
                    cms_credentials.c.domain_id == domain_id,
                    cms_credentials.c.kind == "wordpress",
                )
            ).first()
            if existing:
                credential_id = existing[0]
                conn.execute(
                    sa.update(cms_credentials)
                    .where(
                        cms_credentials.c.id == credential_id,
                        cms_credentials.c.org_id == org_id,
                    )
                    .values(encrypted_payload=encrypted, updated_at=now)
                )
            else:
                credential_id = str(uuid4())
                conn.execute(
                    sa.insert(cms_credentials).values(
                        id=credential_id,
                        org_id=org_id,
                        domain_id=domain_id,
                        kind="wordpress",
                        encrypted_payload=encrypted,
                        created_at=now,
                        updated_at=now,
                    )
                )

            ref = f"cms_credentials:{credential_id}"
            conn.execute(
                sa.update(domains)
                .where(domains.c.id == domain_id, domains.c.org_id == org_id)
                .values(cms_credentials_ref=ref, status="active")
            )

            updated = conn.execute(
                sa.update(integrations)
                .where(integrations.c.org_id == org_id, integrations.c.kind == "wordpress")
                .values(credentials_ref=ref, status="connected", connected_at=now)
            )
            if updated.rowcount == 0:
                conn.execute(
                    sa.insert(integrations).values(
                        id=str(uuid4()),
                        org_id=org_id,
                        kind="wordpress",
                        credentials_ref=ref,
                        status="connected",
                        connected_at=now,
                    )
                )
        return ref

    def get_wordpress(self, ref: str, *, org_id: str) -> WordPressCredentials | None:
        prefix = "cms_credentials:"
        if not ref.startswith(prefix):
            return None
        credential_id = ref.removeprefix(prefix)
        with self._engine.begin() as conn:
            _scope_conn(conn, org_id)
            row = conn.execute(
                sa.select(cms_credentials.c.encrypted_payload).where(
                    cms_credentials.c.id == credential_id,
                    cms_credentials.c.org_id == org_id,
                    cms_credentials.c.kind == "wordpress",
                )
            ).first()
        if row is None:
            return None
        return self._cipher.decrypt_wordpress(row[0])

    def get_wordpress_for_domain(
        self, *, org_id: str, domain_id: str
    ) -> WordPressCredentials | None:
        with self._engine.begin() as conn:
            _scope_conn(conn, org_id)
            row = conn.execute(
                sa.select(domains.c.cms_credentials_ref).where(
                    domains.c.org_id == org_id,
                    domains.c.id == domain_id,
                )
            ).first()
        if row is None or row[0] is None:
            return None
        return self.get_wordpress(str(row[0]), org_id=org_id)


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
                "source_engine": opp.source_engine,
                "status": opp.status,
            }
            for opp in items
        ]
        if not rows:
            return
        with self._engine.begin() as conn:
            _scope_conn(conn, org_id)
            conn.execute(sa.insert(opportunities), rows)


class SqlVisibilityCheckRepository:
    """Postgres/SQLite-backed visibility evidence store.

    Runtime checks are aggregated by prompt+engine, while the DB table stores one
    row per sampled response. Saving expands each aggregate back into raw,
    explainable sample rows.
    """

    def __init__(self, engine: sa.Engine) -> None:
        self._engine = engine

    def save_all(
        self, checks: Sequence[VisibilityCheck], *, org_id: str, domain_id: str
    ) -> None:
        captured_at = datetime.now(UTC).isoformat()
        rows: list[dict[str, object]] = []
        for check in checks:
            needle = check.brand.lower()
            for index, raw in enumerate(check.raw_responses):
                cited = needle in raw.lower()
                usage_id = (
                    check.usage_record_ids[index]
                    if index < len(check.usage_record_ids)
                    else "unknown"
                )
                rows.append(
                    {
                        "id": str(uuid4()),
                        "org_id": org_id,
                        "domain_id": domain_id,
                        "engine": check.engine,
                        "prompt": check.query,
                        "captured_at": captured_at,
                        "brand_cited": cited,
                        "citation_rank": 1 if cited else None,
                        "sentiment": "neutral",
                        "share_of_voice": Decimal("1.0000") if cited else Decimal("0.0000"),
                        "raw_response_ref": f"inline:model_usage:{usage_id}:{raw}",
                    }
                )
        if not rows:
            return
        with self._engine.begin() as conn:
            _scope_conn(conn, org_id)
            conn.execute(sa.insert(visibility_checks), rows)


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


class SqlVoiceProfileRepository:
    """Postgres/SQLite-backed `VoiceProfileRepository`. One profile per domain
    (upserted), so a derived brand voice is cached instead of re-derived each run."""

    def __init__(self, engine: sa.Engine) -> None:
        self._engine = engine

    def get(self, *, org_id: str, domain_id: str) -> str | None:
        with self._engine.begin() as conn:
            _scope_conn(conn, org_id)
            row = conn.execute(
                sa.select(brand_voice_profiles.c.guidelines).where(
                    brand_voice_profiles.c.org_id == org_id,
                    brand_voice_profiles.c.domain_id == domain_id,
                )
            ).first()
        return row[0] if row else None

    def save(self, *, org_id: str, domain_id: str, brand: str, guidelines: str) -> None:
        now = datetime.now(UTC).isoformat()
        with self._engine.begin() as conn:
            _scope_conn(conn, org_id)
            updated = conn.execute(
                sa.update(brand_voice_profiles)
                .where(
                    brand_voice_profiles.c.org_id == org_id,
                    brand_voice_profiles.c.domain_id == domain_id,
                )
                .values(brand=brand, guidelines=guidelines, source="derived", updated_at=now)
            )
            if updated.rowcount == 0:
                conn.execute(
                    sa.insert(brand_voice_profiles).values(
                        id=str(uuid4()), org_id=org_id, domain_id=domain_id,
                        brand=brand, guidelines=guidelines, source="derived", updated_at=now,
                    )
                )


class SqlCrawlSnapshotRepository:
    """Postgres/SQLite-backed crawl ingestion store. A snapshot row captures the
    crawl event and `crawl_pages` stores the queryable site structure/content."""

    def __init__(self, engine: sa.Engine) -> None:
        self._engine = engine

    def save(self, snapshot: SiteSnapshot, *, org_id: str, domain_id: str) -> str:
        snapshot_id = str(uuid4())
        captured_at = datetime.now(UTC).isoformat()
        page_rows = [
            {
                "id": str(uuid4()),
                "org_id": org_id,
                "domain_id": domain_id,
                "snapshot_id": snapshot_id,
                "ordinal": index,
                "url": page.url,
                "title": page.title,
                "headings": list(page.headings),
                "text": page.text,
                "meta_description": page.meta_description,
                "has_structured_data": page.has_structured_data,
                "links": list(page.links),
                "captured_at": captured_at,
            }
            for index, page in enumerate(snapshot.pages)
        ]
        with self._engine.begin() as conn:
            _scope_conn(conn, org_id)
            conn.execute(
                sa.insert(crawl_snapshots).values(
                    id=snapshot_id,
                    org_id=org_id,
                    domain_id=domain_id,
                    captured_at=captured_at,
                    page_count=len(snapshot.pages),
                    storage_ref=f"inline:crawl_pages:{snapshot.domain}",
                )
            )
            if page_rows:
                conn.execute(sa.insert(crawl_pages), page_rows)
        return snapshot_id

    def latest(self, *, org_id: str, domain_id: str) -> SiteSnapshot | None:
        with self._engine.begin() as conn:
            _scope_conn(conn, org_id)
            snapshot = conn.execute(
                sa.select(crawl_snapshots)
                .where(
                    crawl_snapshots.c.org_id == org_id,
                    crawl_snapshots.c.domain_id == domain_id,
                )
                .order_by(crawl_snapshots.c.captured_at.desc())
                .limit(1)
            ).mappings().first()
            if snapshot is None:
                return None
            rows = conn.execute(
                sa.select(crawl_pages)
                .where(crawl_pages.c.snapshot_id == snapshot["id"])
                .order_by(crawl_pages.c.ordinal)
            ).mappings().all()
        storage_ref = str(snapshot["storage_ref"])
        domain = storage_ref.removeprefix("inline:crawl_pages:")
        return SiteSnapshot(
            domain=domain if storage_ref.startswith("inline:crawl_pages:") else "",
            pages=tuple(
                Page(
                    url=row["url"],
                    title=row["title"],
                    headings=tuple(row["headings"] or []),
                    text=row["text"],
                    meta_description=row["meta_description"],
                    has_structured_data=bool(row["has_structured_data"]),
                    links=tuple(row["links"] or []),
                )
                for row in rows
            ),
        )
