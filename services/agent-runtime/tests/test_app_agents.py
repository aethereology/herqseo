from __future__ import annotations

import importlib.util
import sys
import unittest
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

if importlib.util.find_spec("fastapi") is None:
    raise unittest.SkipTest("fastapi is not installed")

from fastapi.testclient import TestClient  # noqa: E402

from queryclear_agent_runtime import (  # noqa: E402
    BrandVoice,
    ClaudeAgentRuntime,
    InMemoryBudgetRepository,
    InMemoryCmsCredentialRepository,
    LoopService,
    ModelResponse,
    PreflightError,
    PublishResult,
    TokenBudget,
    TokenMeter,
    demo_session_runner,
)
from queryclear_agent_runtime.app import create_app  # noqa: E402


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


class _FakePreflightPublisher:
    def __init__(self, *, should_fail: bool = False, **kwargs) -> None:
        self.should_fail = should_fail
        self.kwargs = kwargs

    def preflight(self) -> None:
        if self.should_fail:
            raise PreflightError("switch to pretty permalinks")


def _client(budget_tokens: int = 1_000_000) -> TestClient:
    repo = InMemoryBudgetRepository({"org_1": TokenBudget("org_1", budget_tokens)})
    service = LoopService(
        meter=TokenMeter(repo),
        provider=_FakeProvider(),
        fetcher=_FakeFetcher(),
        voice=BrandVoice("QueryClear", "Plain and direct."),
        publisher=_FakePublisher(),
    )
    # The offline demo session stands in for the Claude Agent SDK; it replays
    # the canonical check-history → run-loop → write-report script.
    runtime = ClaudeAgentRuntime(service, service.meter, session_runner=demo_session_runner)
    return TestClient(create_app(service, agent_runtime=runtime))


def _client_with_wp_factory(factory) -> TestClient:
    repo = InMemoryBudgetRepository({"org_1": TokenBudget("org_1", 1_000_000)})
    cms_credentials = InMemoryCmsCredentialRepository()
    service = LoopService(
        meter=TokenMeter(repo),
        provider=_FakeProvider(),
        fetcher=_FakeFetcher(),
        voice=BrandVoice("QueryClear", "Plain and direct."),
        publisher=_FakePublisher(),
        cms_credentials=cms_credentials,
    )
    return TestClient(
        create_app(
            service,
            wordpress_publisher_factory=factory,
            cms_credentials=cms_credentials,
        )
    )


class AgentApiTest(unittest.TestCase):
    def test_provision_run_results_and_status(self) -> None:
        client = _client()

        created = client.post(
            "/agents", json={"org_id": "org_1", "domain_id": "domain_1"}
        ).json()
        duplicate = client.post(
            "/agents", json={"org_id": "org_1", "domain_id": "domain_1"}
        ).json()

        self.assertEqual(created["agent_id"], duplicate["agent_id"])
        self.assertEqual(created["status"], "active")

        run = client.post(
            f"/agents/{created['agent_id']}/run",
            json={
                "task_class": "operator_run",
                "autonomy_mode": "review",
                "payload": {"domain_url": "https://acme.test", "brand": "Acme"},
            },
        ).json()

        self.assertEqual(run["status"], "needs_approval")
        # IDs come from what the agent's tools actually produced.
        self.assertGreaterEqual(len(run["opportunity_ids"]), 1)
        self.assertEqual(len(run["draft_ids"]), 1)
        self.assertEqual(len(run["usage_record_ids"]), 1)

        results = client.get(f"/agents/{created['agent_id']}/results").json()
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["run_id"], run["run_id"])

        paused = client.post(f"/agents/{created['agent_id']}/pause").json()
        self.assertEqual(paused["status"], "paused")
        resumed = client.post(f"/agents/{created['agent_id']}/resume").json()
        self.assertEqual(resumed["status"], "active")

    def test_memory_and_schedule_endpoints(self) -> None:
        client = _client()
        created = client.post(
            "/agents", json={"org_id": "org_1", "domain_id": "domain_1"}
        ).json()

        memory = client.put(
            f"/agents/{created['agent_id']}/memory",
            json={"memory": {"brand_profile": {"voice": "direct"}}},
        ).json()
        schedule = client.post(
            f"/agents/{created['agent_id']}/schedule", json={"cadence": "weekly"}
        ).json()

        self.assertEqual(memory["brand_profile"], {"voice": "direct"})
        self.assertEqual(schedule["cadence"], "weekly")

    def test_over_budget_run_returns_402(self) -> None:
        client = _client(budget_tokens=10_000)  # below the 200k run reservation
        created = client.post(
            "/agents", json={"org_id": "org_1", "domain_id": "domain_1"}
        ).json()

        response = client.post(
            f"/agents/{created['agent_id']}/run",
            json={
                "task_class": "operator_run",
                "autonomy_mode": "review",
                "payload": {"domain_url": "https://acme.test", "brand": "Acme"},
            },
        )

        self.assertEqual(response.status_code, 402)

    def test_unknown_agent_returns_404(self) -> None:
        client = _client()

        response = client.get("/agents/missing/status")

        self.assertEqual(response.status_code, 404)

    def test_wordpress_preflight_success(self) -> None:
        seen = {}

        def factory(**kwargs):
            seen.update(kwargs)
            return _FakePreflightPublisher(**kwargs)

        client = _client_with_wp_factory(factory)

        response = client.post(
            "/integrations/wordpress/preflight",
            json={
                "base_url": "https://wp.test",
                "username": "editor",
                "app_password": "secret",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["ok"])
        self.assertEqual(seen["base_url"], "https://wp.test")
        self.assertEqual(seen["username"], "editor")

    def test_wordpress_preflight_failure_is_400(self) -> None:
        client = _client_with_wp_factory(
            lambda **kwargs: _FakePreflightPublisher(should_fail=True, **kwargs)
        )

        response = client.post(
            "/integrations/wordpress/preflight",
            json={
                "base_url": "https://wp.test",
                "username": "editor",
                "app_password": "secret",
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("permalinks", response.json()["detail"])

    def test_wordpress_connect_saves_credentials_and_status_hides_secret(self) -> None:
        client = _client_with_wp_factory(lambda **kwargs: _FakePreflightPublisher(**kwargs))

        connected = client.post(
            "/integrations/wordpress/connect",
            json={
                "org_id": "org_1",
                "domain_id": "domain_1",
                "base_url": "https://wp.test",
                "username": "editor",
                "app_password": "secret",
            },
        )
        status = client.get(
            "/integrations/wordpress/status",
            params={"org_id": "org_1", "domain_id": "domain_1"},
        )

        self.assertEqual(connected.status_code, 200)
        body = connected.json()
        self.assertTrue(body["ok"])
        self.assertTrue(body["credentials_ref"])
        self.assertEqual(body["base_url"], "https://wp.test")
        self.assertNotIn("secret", str(body))
        self.assertEqual(status.json(), {
            "connected": True,
            "base_url": "https://wp.test",
            "username": "editor",
        })


if __name__ == "__main__":
    unittest.main()
