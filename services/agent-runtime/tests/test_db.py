from __future__ import annotations

import sys
import unittest
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import sqlalchemy as sa  # noqa: E402

from queryclear_agent_runtime.db import (  # noqa: E402
    SqlBudgetRepository,
    metadata,
    organizations,
)
from queryclear_agent_runtime.metering import (  # noqa: E402
    BudgetExceeded,
    ModelRequest,
    ModelResponse,
    TokenMeter,
    UsageRecord,
)


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


if __name__ == "__main__":
    unittest.main()
