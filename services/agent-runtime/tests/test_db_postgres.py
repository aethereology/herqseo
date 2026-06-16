"""Postgres integration tests for the persistence repos.

Skipped unless ``QC_TEST_DATABASE_URL`` points at a database that already has
migrations 0001+0002 applied and two tenants seeded (the CI `postgres-integration`
job does that prep; see `.github/workflows/ci.yml`). SQLite tests can't catch
Postgres-only type/RLS issues — this is the guard (see memory D13).

The URL must authenticate as a NON-superuser role so row-level security applies.
"""
from __future__ import annotations

import os
import sys
import unittest
from dataclasses import replace
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

URL = os.environ.get("QC_TEST_DATABASE_URL")

ORG_A = "11111111-1111-1111-1111-111111111111"
ORG_B = "22222222-2222-2222-2222-222222222222"
DOM_A = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"


@unittest.skipUnless(URL, "set QC_TEST_DATABASE_URL (non-superuser) to run Postgres integration tests")
class PostgresPersistenceTest(unittest.TestCase):
    def setUp(self) -> None:
        import sqlalchemy as sa  # noqa: F401

        from queryclear_agent_runtime.db import create_engine_from_url

        self.engine = create_engine_from_url(URL)

    def _draft(self, **over):
        from queryclear_agent_runtime.content import ContentPiece

        base = dict(
            id=str(uuid4()), org_id=ORG_A, domain_id=DOM_A, opportunity_id=None,
            title="Improve AI visibility", body="## Answer\nAcme helps.",
            status="pending_approval", model="gpt-4.1", usage_record_id=str(uuid4()),
            cost_usd=Decimal("0.0050"),
        )
        base.update(over)
        return ContentPiece(**base)

    def test_draft_round_trip_upsert_and_timestamp(self) -> None:
        from queryclear_agent_runtime.db import SqlDraftRepository

        repo = SqlDraftRepository(self.engine)
        piece = self._draft()
        repo.save(piece)

        got = repo.get(piece.id, org_id=ORG_A)
        self.assertIsNotNone(got)
        self.assertEqual(got.body, "## Answer\nAcme helps.")
        self.assertEqual(got.cost_usd, Decimal("0.0050"))

        # upsert in place: review -> publish (exercises the 'approved'/'published'
        # enum values and the timestamptz column)
        ts = "2026-06-15T00:00:00+00:00"
        repo.save(replace(piece, status="published", reviewer="f@x.com", published_at=ts))
        got2 = repo.get(piece.id, org_id=ORG_A)
        self.assertEqual(got2.status, "published")
        self.assertEqual(got2.reviewer, "f@x.com")
        self.assertEqual(got2.published_at, ts)

    def test_opportunity_and_fk_linked_draft(self) -> None:
        from queryclear_agent_runtime.db import SqlDraftRepository, SqlOpportunityRepository
        from queryclear_agent_runtime.monitoring import Opportunity

        opp = Opportunity(
            id=str(uuid4()), opportunity_type="content", title="t",
            rationale="r", priority=1, prompt_id="p1",
        )
        SqlOpportunityRepository(self.engine).save_all([opp], org_id=ORG_A, domain_id=DOM_A)
        # a draft referencing that opportunity resolves the FK
        SqlDraftRepository(self.engine).save(self._draft(opportunity_id=opp.id))

    def test_audit_event_round_trip(self) -> None:
        from queryclear_agent_runtime.db import SqlAuditEventRepository
        from queryclear_agent_runtime.publishing import AuditEvent

        repo = SqlAuditEventRepository(self.engine)
        repo.append(
            AuditEvent(
                entity_type="content_piece", entity_id=str(uuid4()), action="publish",
                actor="f@x.com", created_at="2026-06-15T00:00:00+00:00",
                metadata={"usage_record_id": "u-1"},
            ),
            org_id=ORG_A, domain_id=DOM_A,
        )
        events = repo.list(org_id=ORG_A)
        self.assertTrue(events)
        self.assertTrue(any(e.metadata.get("usage_record_id") == "u-1" for e in events))

    def test_voice_profile_cache_round_trip(self) -> None:
        from queryclear_agent_runtime.db import SqlVoiceProfileRepository

        repo = SqlVoiceProfileRepository(self.engine)
        repo.save(org_id=ORG_A, domain_id=DOM_A, brand="Acme", guidelines="Crisp and concrete.")
        self.assertEqual(repo.get(org_id=ORG_A, domain_id=DOM_A), "Crisp and concrete.")
        # upsert in place, and tenant-scoped
        repo.save(org_id=ORG_A, domain_id=DOM_A, brand="Acme", guidelines="Wry.")
        self.assertEqual(repo.get(org_id=ORG_A, domain_id=DOM_A), "Wry.")
        self.assertIsNone(repo.get(org_id=ORG_B, domain_id=DOM_A))

    def test_rls_isolates_tenants(self) -> None:
        import sqlalchemy as sa

        from queryclear_agent_runtime.db import SqlDraftRepository, content_pieces

        # Org A owns a draft.
        piece = self._draft()
        SqlDraftRepository(self.engine).save(piece)

        def visible_as(org: str) -> int:
            # No WHERE clause -> only row-level security governs visibility.
            with self.engine.begin() as conn:
                conn.execute(
                    sa.text("SELECT set_config('app.current_org', :o, true)"), {"o": org}
                )
                return conn.execute(
                    sa.select(sa.func.count()).select_from(content_pieces)
                ).scalar()

        self.assertGreaterEqual(visible_as(ORG_A), 1)
        self.assertEqual(visible_as(ORG_B), 0)
        # And the repo's explicit scope agrees: B cannot fetch A's draft.
        self.assertIsNone(SqlDraftRepository(self.engine).get(piece.id, org_id=ORG_B))


if __name__ == "__main__":
    unittest.main()
