from __future__ import annotations

import sys
import unittest
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import sqlalchemy as sa  # noqa: E402

from queryclear_agent_runtime.content import ContentPiece  # noqa: E402
from queryclear_agent_runtime.db import (  # noqa: E402
    SqlAuditEventRepository,
    SqlBudgetRepository,
    SqlDraftRepository,
    SqlOpportunityRepository,
    metadata,
    opportunities,
    organizations,
)
from queryclear_agent_runtime.metering import (  # noqa: E402
    BudgetExceeded,
    ModelRequest,
    ModelResponse,
    TokenMeter,
    UsageRecord,
)
from queryclear_agent_runtime.monitoring import Opportunity  # noqa: E402
from queryclear_agent_runtime.publishing import AuditEvent  # noqa: E402


def _engine_with_org(*, budget: int = 1000, used: int = 0) -> sa.Engine:
    engine = sa.create_engine("sqlite://", future=True)
    metadata.create_all(engine)
    with engine.begin() as conn:
        conn.execute(
            sa.insert(organizations).values(
                id="org_1", token_budget_monthly=budget, token_used_current_period=used
            )
        )
    return engine


def _usage(total_in: int = 90, total_out: int = 120) -> UsageRecord:
    from datetime import UTC, datetime

    return UsageRecord(
        id="usage-1",
        org_id="org_1",
        domain_id="domain_1",
        task_class="monitoring",
        provider="openai",
        model="gpt-4.1-mini",
        input_tokens=total_in,
        output_tokens=total_out,
        cost_usd=Decimal("0.0012"),
        created_at=datetime.now(UTC),
    )


class SqlBudgetRepositoryTest(unittest.TestCase):
    def test_get_budget_reads_org_row(self) -> None:
        repo = SqlBudgetRepository(_engine_with_org(budget=5000, used=100))
        budget = repo.get_budget("org_1")
        self.assertEqual(budget.monthly_tokens, 5000)
        self.assertEqual(budget.used_tokens, 100)
        self.assertEqual(budget.remaining_tokens, 4900)

    def test_unknown_org_raises(self) -> None:
        repo = SqlBudgetRepository(_engine_with_org())
        with self.assertRaises(BudgetExceeded):
            repo.get_budget("ghost")

    def test_add_usage_writes_row_and_increments(self) -> None:
        engine = _engine_with_org(budget=1000, used=0)
        repo = SqlBudgetRepository(engine)

        updated = repo.add_usage(_usage(90, 120))

        self.assertEqual(updated.used_tokens, 210)
        with engine.connect() as conn:
            rows = conn.execute(sa.text("SELECT provider, input_tokens, output_tokens FROM model_usage")).all()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0][0], "openai")

    def test_meter_runs_through_sql_repo(self) -> None:
        engine = _engine_with_org(budget=1000, used=0)
        meter = TokenMeter(SqlBudgetRepository(engine))

        state = meter.run_metered(
            ModelRequest(
                org_id="org_1", domain_id="domain_1", task_class="content_generation",
                provider="openai", model="gpt-4.1",
                estimated_input_tokens=50, max_output_tokens=100,
            ),
            lambda: ModelResponse(content="ok", input_tokens=40, output_tokens=60, cost_usd=Decimal("0.01")),
        )

        self.assertEqual(state.budget.used_tokens, 100)
        with engine.connect() as conn:
            count = conn.execute(sa.text("SELECT count(*) FROM model_usage")).scalar()
        self.assertEqual(count, 1)


def _empty_engine() -> sa.Engine:
    engine = sa.create_engine("sqlite://", future=True)
    metadata.create_all(engine)
    return engine


def _piece(status: str = "pending_approval", reviewer=None, published_at=None) -> ContentPiece:
    return ContentPiece(
        id="cp-1", org_id="org_1", domain_id="domain_1", opportunity_id="opp-1",
        title="Improve AI visibility", body="## Answer\nQueryClear helps.",
        status=status, model="gpt-4.1", usage_record_id="usage-1",
        cost_usd=Decimal("0.0050"), reviewer=reviewer, published_at=published_at,
    )


class SqlDraftRepositoryTest(unittest.TestCase):
    def test_save_then_get_round_trips(self) -> None:
        repo = SqlDraftRepository(_empty_engine())
        repo.save(_piece())
        got = repo.get("cp-1", org_id="org_1")
        self.assertIsNotNone(got)
        self.assertEqual(got.title, "Improve AI visibility")
        self.assertEqual(got.body, "## Answer\nQueryClear helps.")
        self.assertEqual(got.cost_usd, Decimal("0.0050"))

    def test_get_is_tenant_scoped(self) -> None:
        repo = SqlDraftRepository(_empty_engine())
        repo.save(_piece())
        self.assertIsNone(repo.get("cp-1", org_id="other_org"))

    def test_save_upserts_in_place(self) -> None:
        engine = _empty_engine()
        repo = SqlDraftRepository(engine)
        repo.save(_piece())
        repo.save(_piece(status="published", reviewer="f@x.com", published_at="2026-06-15T00:00:00+00:00"))
        got = repo.get("cp-1", org_id="org_1")
        self.assertEqual(got.status, "published")
        self.assertEqual(got.reviewer, "f@x.com")
        self.assertEqual(got.published_at, "2026-06-15T00:00:00+00:00")
        from queryclear_agent_runtime.db import content_pieces
        with engine.connect() as conn:
            count = conn.execute(sa.select(sa.func.count()).select_from(content_pieces)).scalar()
        self.assertEqual(count, 1)


class SqlOpportunityRepositoryTest(unittest.TestCase):
    def test_save_all_writes_rows(self) -> None:
        engine = _empty_engine()
        SqlOpportunityRepository(engine).save_all(
            [Opportunity(id="opp-1", opportunity_type="content", title="t",
                         rationale="r", priority=1, prompt_id="p1")],
            org_id="org_1", domain_id="domain_1",
        )
        with engine.connect() as conn:
            row = conn.execute(sa.select(opportunities.c.source_prompt, opportunities.c.type)).first()
        self.assertEqual(row[0], "p1")
        self.assertEqual(row[1], "content")

    def test_save_all_empty_is_noop(self) -> None:
        engine = _empty_engine()
        SqlOpportunityRepository(engine).save_all([], org_id="org_1", domain_id="domain_1")
        with engine.connect() as conn:
            count = conn.execute(sa.select(sa.func.count()).select_from(opportunities)).scalar()
        self.assertEqual(count, 0)


class SqlAuditEventRepositoryTest(unittest.TestCase):
    def _event(self) -> AuditEvent:
        return AuditEvent(
            entity_type="content_piece", entity_id="cp-1", action="publish",
            actor="f@x.com", created_at="2026-06-15T00:00:00+00:00",
            metadata={"usage_record_id": "usage-1"},
        )

    def test_append_then_list_round_trips(self) -> None:
        repo = SqlAuditEventRepository(_empty_engine())
        repo.append(self._event(), org_id="org_1", domain_id="domain_1")
        events = repo.list(org_id="org_1")
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].action, "publish")
        self.assertEqual(events[0].metadata["usage_record_id"], "usage-1")

    def test_list_is_tenant_scoped(self) -> None:
        repo = SqlAuditEventRepository(_empty_engine())
        repo.append(self._event(), org_id="org_1", domain_id="domain_1")
        self.assertEqual(repo.list(org_id="other_org"), [])


if __name__ == "__main__":
    unittest.main()
