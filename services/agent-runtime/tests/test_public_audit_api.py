from __future__ import annotations

import importlib.util
import io
import json
import os
import unittest
from email.message import Message
from pathlib import Path
from unittest.mock import patch

from queryclear_agent_runtime.crawl import CrawlBudgetExceeded


_API_PATH = Path(__file__).resolve().parents[1] / "api" / "audit.py"
_SPEC = importlib.util.spec_from_file_location("queryclear_public_audit_api", _API_PATH)
assert _SPEC and _SPEC.loader
audit_api = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(audit_api)
_SECRET = "shared-secret-0123456789-0123456789"


def _request(body: object, *, key: str | None, length: int | None = None):
    raw = json.dumps(body).encode("utf-8")
    instance = object.__new__(audit_api.handler)
    headers = Message()
    headers["content-type"] = "application/json"
    headers["content-length"] = str(len(raw) if length is None else length)
    if key is not None:
        headers["x-queryclear-runtime-key"] = key
    instance.headers = headers
    instance.rfile = io.BytesIO(raw)
    instance.wfile = io.BytesIO()
    result: dict[str, object] = {"headers": {}}
    instance.send_response = lambda status: result.update(status=status)
    instance.send_header = lambda name, value: result["headers"].update({name.lower(): value})
    instance.end_headers = lambda: None
    instance.log_error = lambda *args, **kwargs: None
    return instance, result


class _FakeService:
    def __init__(self, result=None, error: Exception | None = None) -> None:
        self.result = result
        self.error = error
        self.calls: list[dict[str, object]] = []

    def audit(self, domain_url, brand, **kwargs):
        self.calls.append({"domain_url": domain_url, "brand": brand, **kwargs})
        if self.error:
            raise self.error
        return self.result


class PublicAuditApiTest(unittest.TestCase):
    def tearDown(self) -> None:
        audit_api._service = None

    def test_public_service_explicitly_disables_demo_mode(self) -> None:
        sentinel = object()
        with patch.object(audit_api, "build_service", return_value=sentinel) as build:
            self.assertIs(audit_api._get_service(), sentinel)
        build.assert_called_once_with(allow_demo=False)

    def test_missing_server_secret_fails_closed(self) -> None:
        request, result = _request({"domain_url": "https://example.com"}, key=None)
        with patch.dict(os.environ, {}, clear=True):
            request.do_POST()
        self.assertEqual(result["status"], 503)

    def test_wrong_shared_secret_is_unauthorized(self) -> None:
        request, result = _request({"domain_url": "https://example.com"}, key="wrong")
        with patch.dict(os.environ, {"AGENT_RUNTIME_SHARED_SECRET": _SECRET}, clear=True):
            request.do_POST()
        self.assertEqual(result["status"], 401)

    def test_public_endpoint_pins_tenant_and_sample_count(self) -> None:
        service = _FakeService(result={"report": True})
        request, result = _request(
            {
                "domain_url": "https://Example.com/private/path",
                "org_id": "attacker-org",
                "domain_id": "attacker-domain",
                "samples": 99,
            },
            key=_SECRET,
        )
        env = {
            "AGENT_RUNTIME_SHARED_SECRET": _SECRET,
            "QUERYCLEAR_DEV_ORG_ID": "org_public",
            "QUERYCLEAR_PUBLIC_DOMAIN_ID": "domain_public",
        }
        with (
            patch.dict(os.environ, env, clear=True),
            patch.object(audit_api, "_get_service", return_value=service),
            patch.object(audit_api, "_report_json", side_effect=lambda report: report),
        ):
            request.do_POST()

        self.assertEqual(result["status"], 200)
        self.assertEqual(result["headers"]["cache-control"], "no-store")
        self.assertEqual(
            service.calls,
            [
                {
                    "domain_url": "https://example.com/",
                    "brand": "Example",
                    "org_id": "org_public",
                    "domain_id": "domain_public",
                    "samples": 1,
                }
            ],
        )

    def test_private_url_is_rejected_before_service_work(self) -> None:
        service = _FakeService(result={"report": True})
        request, result = _request(
            {"domain_url": "http://169.254.169.254/latest/meta-data/"}, key=_SECRET
        )
        with (
            patch.dict(os.environ, {"AGENT_RUNTIME_SHARED_SECRET": _SECRET}, clear=True),
            patch.object(audit_api, "_get_service", return_value=service),
        ):
            request.do_POST()
        self.assertEqual(result["status"], 400)
        self.assertEqual(service.calls, [])

    def test_internal_exception_detail_is_not_returned(self) -> None:
        service = _FakeService(error=RuntimeError("secret token=abc"))
        request, result = _request({"domain_url": "https://example.com"}, key=_SECRET)
        with (
            patch.dict(os.environ, {"AGENT_RUNTIME_SHARED_SECRET": _SECRET}, clear=True),
            patch.object(audit_api, "_get_service", return_value=service),
        ):
            request.do_POST()
        body = json.loads(request.wfile.getvalue())
        self.assertEqual(result["status"], 500)
        self.assertNotIn("secret", body["error"].lower())
        self.assertNotIn("token", body["error"].lower())

    def test_crawl_deadline_returns_a_safe_gateway_timeout(self) -> None:
        service = _FakeService(error=CrawlBudgetExceeded("internal timing detail"))
        request, result = _request({"domain_url": "https://example.com"}, key=_SECRET)
        with (
            patch.dict(os.environ, {"AGENT_RUNTIME_SHARED_SECRET": _SECRET}, clear=True),
            patch.object(audit_api, "_get_service", return_value=service),
        ):
            request.do_POST()

        body = json.loads(request.wfile.getvalue())
        self.assertEqual(result["status"], 504)
        self.assertEqual(body["error"], "The website crawl exceeded its time limit.")
        self.assertNotIn("internal", body["error"].lower())

    def test_oversized_request_is_rejected_without_reading_it(self) -> None:
        request, result = _request(
            {"domain_url": "https://example.com"}, key=_SECRET, length=8_193
        )
        with patch.dict(os.environ, {"AGENT_RUNTIME_SHARED_SECRET": _SECRET}, clear=True):
            request.do_POST()
        self.assertEqual(result["status"], 413)


if __name__ == "__main__":
    unittest.main()
