"""Vercel Python function: the public, stateless audit endpoint.

Reuses the runtime's own service wiring (build_service) and JSON serializer
(_report_json) so this stays a single source of truth with the rest of the
product. Deployed as its own Vercel project rooted at services/agent-runtime/;
the marketing site calls POST {AGENT_RUNTIME_URL}/api/audit server-to-server.

A single BaseHTTPRequestHandler (one file = one endpoint) is the most reliable
Vercel Python shape — no ASGI sub-path routing to get wrong.
"""
import json
import os
import sys
import hmac
from http.server import BaseHTTPRequestHandler

# Make the package importable on Vercel (src/ layout, no editable install).
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from queryclear_agent_runtime.app import _brand_from_url, _report_json  # noqa: E402
from queryclear_agent_runtime.crawl import (  # noqa: E402
    CrawlBudgetExceeded,
    CrawlFetchError,
    UnsafeUrlError,
    normalize_public_site_url,
)
from queryclear_agent_runtime.metering import BudgetExceeded  # noqa: E402
from queryclear_agent_runtime.serve import build_service  # noqa: E402

# Build once per warm instance; reused across invocations.
_service = None
_MAX_REQUEST_BYTES = 8_192
_RUNTIME_KEY_HEADER = "x-queryclear-runtime-key"


def _get_service():
    global _service
    if _service is None:
        # The public endpoint must never emit the fixed offline-demo report.
        _service = build_service(allow_demo=False)
    return _service


class handler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:  # noqa: N802 (Vercel/BaseHTTPRequestHandler API)
        expected_key = os.environ.get("AGENT_RUNTIME_SHARED_SECRET", "").strip()
        if len(expected_key) < 32:
            return self._send(503, {"error": "Audit service is not configured."})
        supplied_key = self.headers.get(_RUNTIME_KEY_HEADER, "")
        if not hmac.compare_digest(supplied_key, expected_key):
            return self._send(401, {"error": "Unauthorized."})

        content_type = self.headers.get("content-type", "").lower()
        if not content_type.startswith("application/json"):
            return self._send(415, {"error": "Content-Type must be application/json."})
        try:
            length = int(self.headers.get("content-length") or 0)
        except ValueError:
            return self._send(400, {"error": "Invalid request length."})
        if length < 0 or length > _MAX_REQUEST_BYTES:
            return self._send(413, {"error": "Request body is too large."})
        raw = self.rfile.read(length) if length else b"{}"
        try:
            body = json.loads(raw or b"{}")
        except (ValueError, TypeError):
            return self._send(400, {"error": "Invalid JSON body."})
        if not isinstance(body, dict):
            return self._send(400, {"error": "JSON body must be an object."})

        try:
            domain_url = normalize_public_site_url(str(body.get("domain_url") or "").strip())
        except UnsafeUrlError as exc:
            return self._send(400, {"error": str(exc)})

        # This endpoint is one stateless public-audit tenant. Requesters cannot
        # choose a tenant or increase samples/cost through the JSON body.
        org_id = os.environ.get("QUERYCLEAR_DEV_ORG_ID", "org_public_queryclear")
        domain_id = os.environ.get("QUERYCLEAR_PUBLIC_DOMAIN_ID", "domain_public_queryclear")
        brand = _brand_from_url(domain_url)

        try:
            report = _get_service().audit(
                domain_url, brand, org_id=org_id, domain_id=domain_id, samples=1
            )
            return self._send(200, _report_json(report))
        except UnsafeUrlError as exc:
            return self._send(400, {"error": str(exc)})
        except CrawlBudgetExceeded:
            return self._send(504, {"error": "The website crawl exceeded its time limit."})
        except CrawlFetchError:
            return self._send(422, {"error": "The public website could not be fetched safely."})
        except BudgetExceeded:
            return self._send(429, {"error": "The audit budget is temporarily exhausted."})
        except Exception:
            self.log_error("audit failed")
            return self._send(500, {"error": "The audit could not be completed."})

    def _send(self, status: int, payload: dict) -> None:
        data = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(data)))
        self.send_header("cache-control", "no-store")
        self.send_header("x-content-type-options", "nosniff")
        self.end_headers()
        self.wfile.write(data)
