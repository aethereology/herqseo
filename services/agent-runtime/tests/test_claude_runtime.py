from __future__ import annotations

import sys
import unittest
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from queryclear_agent_runtime import (  # noqa: E402
    AGENT_TOOL_NAMES,
    AgentNotFound,
    AgentTask,
    ApprovalRequired,
    BrandVoice,
    BudgetExceeded,
    ClaudeAgentRuntime,
    InMemoryBudgetRepository,
    LoopService,
    ModelResponse,
    PublishResult,
    TokenBudget,
    TokenMeter,
)


class _FakeFetcher:
    def fetch(self, url: str) -> str:
        return "<html><head><title>Acme</title></head><body><p>Acme copy.</p></body></html>"


class _FakeProvider:
    def complete(self, request, prompt, *, system=None) -> ModelResponse:
        return ModelResponse(
            content="Use a competitor.",
            input_tokens=10,
            output_tokens=20,
            cost_usd=Decimal("0.001"),
        )


class _FakePublisher:
    def publish(self, *, title, body, status="draft") -> PublishResult:
        return PublishResult(cms_post_id="1", url="https://staging.test/?p=1", status=status)


def _scripted_runner(script):
    """Fake session runner: replays canned tool calls against the REAL tool
    closures, so collector/metering behavior is exercised without the SDK."""
    contexts: list = []

    def runner(context) -> ModelResponse:
        contexts.append(context)
        for name, kwargs in script:
            context.tools[name](**kwargs)
        return ModelResponse(
            content="agent report",
            input_tokens=1_000,
            output_tokens=500,
            cost_usd=Decimal("0.0100"),
        )

    return runner, contexts


def _service(budget_tokens: int = 1_000_000) -> tuple[LoopService, InMemoryBudgetRepository]:
    repo = InMemoryBudgetRepository({"org_1": TokenBudget("org_1", budget_tokens)})
    service = LoopService(
        meter=TokenMeter(repo),
        provider=_FakeProvider(),
        fetcher=_FakeFetcher(),
        voice=BrandVoice("QueryClear", "Plain and direct."),
        publisher=_FakePublisher(),
    )
    return service, repo


def _runtime(
    budget_tokens: int = 1_000_000, script=None
) -> tuple[ClaudeAgentRuntime, InMemoryBudgetRepository, list]:
    service, repo = _service(budget_tokens)
    runner, contexts = _scripted_runner(
        script
        if script is not None
        else [
            ("get_recent_results", {}),
            ("run_operator_loop", {}),
            ("write_run_report", {"summary": "ran the loop", "learnings": "brand uncited"}),
        ]
    )
    runtime = ClaudeAgentRuntime(service, service.meter, session_runner=runner)
    return runtime, repo, contexts


_TASK = AgentTask(
    task_class="operator_run",
    autonomy_mode="review",
    payload={"domain_url": "https://acme.test", "brand": "Acme"},
)


class ClaudeAgentRuntimeBookkeepingTest(unittest.TestCase):
    def test_provision_is_idempotent_per_org_domain(self) -> None:
        runtime, _, _ = _runtime()

        first = runtime.provision("org_1", "domain_1")
        second = runtime.provision("org_1", "domain_1")
        other = runtime.provision("org_1", "domain_2")

        self.assertEqual(first.agent_id, second.agent_id)
        self.assertNotEqual(first.agent_id, other.agent_id)
        self.assertEqual(len(runtime.list(org_id="org_1")), 2)

    def test_list_filters_by_org_and_domain(self) -> None:
        runtime, _, _ = _runtime()
        runtime.provision("org_1", "domain_1")
        runtime.provision("org_1", "domain_2")
        runtime.provision("org_2", "domain_1")

        self.assertEqual(len(runtime.list()), 3)
        self.assertEqual(len(runtime.list(org_id="org_1")), 2)
        self.assertEqual(len(runtime.list(domain_id="domain_1")), 2)
        self.assertEqual(len(runtime.list(org_id="org_1", domain_id="domain_1")), 1)

    def test_memory_is_isolated_per_agent(self) -> None:
        runtime, _, _ = _runtime()
        one = runtime.provision("org_1", "domain_1")
        two = runtime.provision("org_1", "domain_2")

        runtime.set_memory(one, {"brand_profile": {"voice": "direct"}})

        self.assertEqual(runtime.get_memory(one)["brand_profile"], {"voice": "direct"})
        self.assertEqual(runtime.get_memory(two)["brand_profile"], {})

    def test_schedule_resume_and_lookup(self) -> None:
        runtime, _, _ = _runtime()
        handle = runtime.provision("org_1", "domain_1")

        runtime.schedule(handle, "weekly")
        paused = runtime.pause(handle)
        resumed = runtime.resume(paused)

        self.assertEqual(runtime.schedule_for(handle), "weekly")
        self.assertEqual(resumed.status.value, "active")
        self.assertEqual(runtime.get(handle.agent_id), resumed)

    def test_unknown_agent_raises(self) -> None:
        runtime, _, _ = _runtime()
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


class ClaudeAgentRuntimeRunTest(unittest.TestCase):
    def test_review_run_produces_real_work_and_needs_approval(self) -> None:
        runtime, repo, contexts = _runtime()
        handle = runtime.provision("org_1", "domain_1")

        result = runtime.run(handle, _TASK)

        self.assertEqual(result.status, "needs_approval")
        # IDs come from what the tools actually did, not from the payload.
        self.assertGreaterEqual(len(result.opportunity_ids), 1)
        self.assertEqual(len(result.draft_ids), 1)
        self.assertEqual(len(runtime.results(handle)), 1)
        # The session got exactly the three sanctioned tools — no publish tool.
        self.assertEqual(set(contexts[0].tools), set(AGENT_TOOL_NAMES))

    def test_run_is_metered_as_one_agent_run_record(self) -> None:
        runtime, repo, _ = _runtime()
        handle = runtime.provision("org_1", "domain_1")

        result = runtime.run(handle, _TASK)

        agent_records = [r for r in repo.records if r.task_class == "agent_run"]
        self.assertEqual(len(agent_records), 1)
        record = agent_records[0]
        self.assertEqual(record.input_tokens, 1_000)
        self.assertEqual(record.output_tokens, 500)
        self.assertEqual(record.provider, "anthropic")
        self.assertEqual(result.usage_record_ids, [record.id])
        # The loop's own model calls still meter themselves.
        self.assertGreater(len(repo.records), 1)

    def test_over_budget_run_is_rejected_before_the_session_starts(self) -> None:
        # Budget far below the run reservation (default 200k tokens).
        runtime, repo, contexts = _runtime(budget_tokens=10_000)
        handle = runtime.provision("org_1", "domain_1")

        with self.assertRaises(BudgetExceeded):
            runtime.run(handle, _TASK)

        self.assertEqual(contexts, [], "session must never start when unaffordable")
        self.assertEqual(repo.records, [])
        self.assertEqual(len(runtime.results(handle)), 0)

    def test_paused_agent_fails_without_spending(self) -> None:
        runtime, repo, contexts = _runtime()
        handle = runtime.provision("org_1", "domain_1")
        paused = runtime.pause(handle)

        result = runtime.run(paused, _TASK)

        self.assertEqual(result.status, "failed")
        self.assertEqual(contexts, [])
        self.assertEqual(repo.records, [])

    def test_agent_cannot_publish_the_draft_it_produced(self) -> None:
        runtime, _, contexts = _runtime()
        service = runtime._service
        handle = runtime.provision("org_1", "domain_1")

        result = runtime.run(handle, _TASK)

        draft_id = result.draft_ids[0]
        draft = service.get_draft(draft_id, org_id="org_1")
        self.assertEqual(draft.status, "pending_approval")
        # The review gate holds even if the agent's output reaches publish.
        with self.assertRaises(ApprovalRequired):
            service.publish(draft_id, org_id="org_1", actor="agent")

    def test_report_and_learnings_land_in_memory(self) -> None:
        runtime, _, _ = _runtime()
        handle = runtime.provision("org_1", "domain_1")

        runtime.run(handle, _TASK)

        memory = runtime.get_memory(handle)
        self.assertEqual(memory["learnings"], ["brand uncited"])
        self.assertEqual(memory["action_history"][-1]["report"], "ran the loop")

    def test_loop_is_pinned_to_the_task_domain(self) -> None:
        # A task without domain_url/brand: the loop tool refuses instead of
        # letting the agent choose a target.
        runtime, _, _ = _runtime(script=[("run_operator_loop", {})])
        handle = runtime.provision("org_1", "domain_1")

        result = runtime.run(
            handle, AgentTask(task_class="operator_run", autonomy_mode="review")
        )

        self.assertEqual(result.opportunity_ids, [])
        self.assertEqual(result.draft_ids, [])


if __name__ == "__main__":
    unittest.main()
