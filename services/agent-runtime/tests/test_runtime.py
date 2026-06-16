from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from queryclear_agent_runtime import AgentNotFound, AgentTask, HermesAgentRuntime  # noqa: E402


class HermesAgentRuntimeTest(unittest.TestCase):
    def test_provision_is_idempotent_per_org_domain(self) -> None:
        runtime = HermesAgentRuntime()

        first = runtime.provision("org_1", "domain_1")
        second = runtime.provision("org_1", "domain_1")
        other = runtime.provision("org_1", "domain_2")

        self.assertEqual(first.agent_id, second.agent_id)
        self.assertNotEqual(first.agent_id, other.agent_id)
        self.assertEqual(len(runtime.list(org_id="org_1")), 2)

    def test_list_filters_by_org_and_domain(self) -> None:
        runtime = HermesAgentRuntime()
        runtime.provision("org_1", "domain_1")
        runtime.provision("org_1", "domain_2")
        runtime.provision("org_2", "domain_1")

        self.assertEqual(len(runtime.list()), 3)
        self.assertEqual(len(runtime.list(org_id="org_1")), 2)
        self.assertEqual(len(runtime.list(domain_id="domain_1")), 2)
        self.assertEqual(len(runtime.list(org_id="org_1", domain_id="domain_1")), 1)

    def test_review_mode_run_needs_approval(self) -> None:
        runtime = HermesAgentRuntime()
        handle = runtime.provision("org_1", "domain_1")

        result = runtime.run(
            handle,
            AgentTask(
                task_class="monitoring",
                autonomy_mode="review",
                payload={
                    "opportunity_ids": ["opp-1"],
                    "draft_ids": ["draft-1"],
                    "usage_record_ids": ["usage-1"],
                },
            ),
        )

        self.assertEqual(result.status, "needs_approval")
        self.assertEqual(result.agent_id, handle.agent_id)
        self.assertEqual(result.org_id, "org_1")
        self.assertEqual(result.domain_id, "domain_1")
        self.assertEqual(result.task_class, "monitoring")
        self.assertEqual(result.opportunity_ids, ["opp-1"])
        self.assertEqual(result.draft_ids, ["draft-1"])
        self.assertEqual(result.usage_record_ids, ["usage-1"])
        self.assertEqual(runtime.status(handle).value, "active")
        self.assertEqual(len(runtime.results(handle)), 1)

    def test_pause_blocks_runs(self) -> None:
        runtime = HermesAgentRuntime()
        handle = runtime.provision("org_1", "domain_1")
        paused = runtime.pause(handle)

        result = runtime.run(paused, AgentTask(task_class="monitoring", autonomy_mode="review"))

        self.assertEqual(result.status, "failed")
        self.assertEqual(runtime.status(paused).value, "paused")

    def test_memory_is_isolated_per_agent(self) -> None:
        runtime = HermesAgentRuntime()
        one = runtime.provision("org_1", "domain_1")
        two = runtime.provision("org_1", "domain_2")

        runtime.set_memory(one, {"brand_profile": {"voice": "direct"}})

        self.assertEqual(runtime.get_memory(one)["brand_profile"], {"voice": "direct"})
        self.assertEqual(runtime.get_memory(two)["brand_profile"], {})

    def test_schedule_resume_and_lookup(self) -> None:
        runtime = HermesAgentRuntime()
        handle = runtime.provision("org_1", "domain_1")

        runtime.schedule(handle, "weekly")
        paused = runtime.pause(handle)
        resumed = runtime.resume(paused)

        self.assertEqual(runtime.schedule_for(handle), "weekly")
        self.assertEqual(resumed.status.value, "active")
        self.assertEqual(runtime.get(handle.agent_id), resumed)

    def test_unknown_agent_raises(self) -> None:
        runtime = HermesAgentRuntime()
        handle = runtime.provision("org_1", "domain_1")
        ghost = type(handle)(
            agent_id="missing",
            org_id=handle.org_id,
            domain_id=handle.domain_id,
            status=handle.status,
            memory_store_ref=handle.memory_store_ref,
        )

        with self.assertRaises(AgentNotFound):
            runtime.status(ghost)


if __name__ == "__main__":
    unittest.main()
