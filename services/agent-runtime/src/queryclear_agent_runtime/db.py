"""SQLAlchemy-backed persistence for the money path (model usage + token budget).

Imports SQLAlchemy, so this module is NOT imported by the package ``__init__`` —
load it directly (``from queryclear_agent_runtime.db import ...``) and install the
``db`` extra. Columns mirror packages/db (the migration is the source of truth);
types are kept portable so the same code runs on Postgres and on SQLite (tests).
"""
from __future__ import annotations

import sqlalchemy as sa

from .metering import BudgetExceeded, TokenBudget, UsageRecord

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


def create_engine_from_url(url: str) -> sa.Engine:
    return sa.create_engine(url, future=True)


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
