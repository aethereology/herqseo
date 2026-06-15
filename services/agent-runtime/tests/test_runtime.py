from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from queryclear_agent_runtime import AgentTask, HermesAgentRuntime  # noqa: E402


class HermesAgentRuntimeTest(unittest.TestCase):
    def test_review_mode_run_needs_approval(self) -> None:
        runtime = HermesAgentRuntime()
        handle = runtime.provision("org_1", "domain_1")

        result = runtime.run(handle, AgentTask(task_class="monitoring", autonomy_mode="review"))

        self.assertEqual(result.status, "needs_approval")
        self.assertEqual(runtime.status(handle).value, "active")

    def test_pause_blocks_runs(self) -> None:
        runtime = HermesAgentRuntime()
        handle = runtime.provision("org_1", "domain_1")
        paused = runtime.pause(handle)

        result = runtime.run(paused, AgentTask(task_class="monitoring", autonomy_mode="review"))

        self.assertEqual(result.status, "failed")
        self.assertEqual(runtime.status(paused).value, "paused")


if __name__ == "__main__":
    unittest.main()
