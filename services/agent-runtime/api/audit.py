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
from http.server import BaseHTTPRequestHandler

# Make the package importable on Vercel (src/ layout, no editable install).
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from queryclear_agent_runtime.app import _brand_from_url, _report_json  # noqa: E402
from queryclear_agent_runtime.serve import build_service  # noqa: E402

# Build once per warm instance; reused across invocations.
_service = None


def _get_service():
    global _service
    if _service is None:
        _service = build_service()
    return _service


class handler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:  # noqa: N802 (Vercel/BaseHTTPRequestHandler API)
        length = int(self.headers.get("content-length") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        try:
            body = json.loads(raw or b"{}")
        except (ValueError, TypeError):
            return self._send(400, {"error": "Invalid JSON body."})

        domain_url = str(body.get("domain_url") or "").strip()
        if not domain_url:
            return self._send(400, {"error": "domain_url is required"})

        org_id = body.get("org_id") or "org_dev_queryclear"
        domain_id = body.get("domain_id") or "domain_dev_queryclear"
        brand = body.get("brand") or _brand_from_url(domain_url)
        try:
            samples = max(1, int(body.get("samples") or 1))
        except (ValueError, TypeError):
            samples = 1

        try:
            report = _get_service().audit(
                domain_url, brand, org_id=org_id, domain_id=domain_id, samples=samples
            )
            return self._send(200, _report_json(report))
        except Exception as exc:  # surface a clean message; never leak a stack
            return self._send(500, {"error": f"{type(exc).__name__}: {exc}"})

    def _send(self, status: int, payload: dict) -> None:
        data = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)
