from __future__ import annotations

import sys
import unittest
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from queryclear_agent_runtime import (  # noqa: E402
    ApprovalRequired,
    AuditEvent,
    ContentPiece,
    PreflightError,
    PublishResult,
    StagingOnlyError,
    WordPressPublisher,
    publish_content,
)


class _FakeResponse:
    def __init__(self, data: dict) -> None:
        self._data = data

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._data


class _FakeHttp:
    def __init__(self, data: dict) -> None:
        self._data = data
        self.calls: list[dict] = []

    def post(self, url, *, json=None, auth=None, timeout=None) -> _FakeResponse:
        self.calls.append({"url": url, "json": json, "auth": auth})
        return _FakeResponse(self._data)


class _FakePublisher:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def publish(self, *, title: str, body: str, status: str = "draft") -> PublishResult:
        self.calls.append({"title": title, "body": body, "status": status})
        return PublishResult(cms_post_id="101", url="https://site.test/?p=101", status=status)


def _piece(status: str = "approved") -> ContentPiece:
    return ContentPiece(
        id="cp-opp-vp-0",
        org_id="org_1",
        domain_id="domain_1",
        opportunity_id="opp-vp-0",
        title="Improve AI visibility for: best invoice automation for saas",
        body="## Direct answer\nQueryClear automates invoices...",
        status=status,
        model="gpt-4.1",
        usage_record_id="usage-123",
        cost_usd=Decimal("0.0050"),
        reviewer="founder@x.com" if status == "approved" else None,
    )


class WordPressPublisherTest(unittest.TestCase):
    def test_publishes_as_draft(self) -> None:
        http = _FakeHttp({"id": 55, "link": "https://site.test/?p=55", "status": "draft"})
        wp = WordPressPublisher(
            base_url="https://site.test/", username="u", app_password="p", client=http
        )

        result = wp.publish(title="Hello", body="Body")

        self.assertEqual(result.cms_post_id, "55")
        self.assertEqual(result.status, "draft")
        call = http.calls[0]
        self.assertEqual(call["url"], "https://site.test/wp-json/wp/v2/posts")
        self.assertEqual(call["json"]["status"], "draft")
        self.assertEqual(call["auth"], ("u", "p"))

    def test_refuses_live_publish(self) -> None:
        http = _FakeHttp({})
        wp = WordPressPublisher(base_url="https://site.test", username="u", app_password="p", client=http)

        with self.assertRaises(StagingOnlyError):
            wp.publish(title="Hello", body="Body", status="publish")

        self.assertEqual(http.calls, [])  # never hit the network


class _FakeGetResponse:
    def __init__(self, status_code: int, content_type: str) -> None:
        self.status_code = status_code
        self.headers = {"content-type": content_type}

    def json(self) -> dict:
        return {"id": 1, "name": "qcadmin"}


class _FakeGetHttp:
    def __init__(self, response=None, raise_exc=None) -> None:
        self._response = response
        self._raise = raise_exc
        self.calls: list[dict] = []

    def get(self, url, *, auth=None, timeout=None):
        self.calls.append({"url": url, "auth": auth})
        if self._raise is not None:
            raise self._raise
        return self._response


class WordPressPreflightTest(unittest.TestCase):
    def _wp(self, http) -> WordPressPublisher:
        return WordPressPublisher(
            base_url="https://site.test/", username="u", app_password="p", client=http
        )

    def test_ok_when_rest_returns_json(self) -> None:
        http = _FakeGetHttp(_FakeGetResponse(200, "application/json; charset=UTF-8"))
        self._wp(http).preflight()  # no raise
        self.assertEqual(http.calls[0]["url"], "https://site.test/wp-json/wp/v2/users/me?context=edit")
        self.assertEqual(http.calls[0]["auth"], ("u", "p"))

    def test_auth_failure_is_actionable(self) -> None:
        http = _FakeGetHttp(_FakeGetResponse(401, "application/json"))
        with self.assertRaises(PreflightError) as ctx:
            self._wp(http).preflight()
        self.assertIn("application password", str(ctx.exception))

    def test_plain_permalinks_detected(self) -> None:
        http = _FakeGetHttp(_FakeGetResponse(200, "text/html; charset=UTF-8"))
        with self.assertRaises(PreflightError) as ctx:
            self._wp(http).preflight()
        self.assertIn("permalinks", str(ctx.exception).lower())

    def test_unreachable_site(self) -> None:
        http = _FakeGetHttp(raise_exc=OSError("connection refused"))
        with self.assertRaises(PreflightError) as ctx:
            self._wp(http).preflight()
        self.assertIn("reach", str(ctx.exception).lower())


class PublishContentTest(unittest.TestCase):
    def test_publishes_approved_piece_and_audits(self) -> None:
        publisher = _FakePublisher()
        audit: list[AuditEvent] = []

        outcome = publish_content(
            publisher, _piece("approved"),
            autonomy_mode="review", actor="founder@x.com", audit_log=audit,
        )

        self.assertEqual(outcome.piece.status, "published")
        self.assertEqual(outcome.piece.cms_post_id, "101")
        self.assertIsNotNone(outcome.piece.published_at)
        self.assertEqual(publisher.calls[0]["status"], "draft")

        self.assertEqual(len(audit), 1)
        event = audit[0]
        self.assertEqual(event.action, "publish")
        self.assertEqual(event.entity_id, "cp-opp-vp-0")
        # audit links publish -> approver and the metered model call
        self.assertEqual(event.metadata["approved_by"], "founder@x.com")
        self.assertEqual(event.metadata["usage_record_id"], "usage-123")
        self.assertEqual(event.metadata["cms_post_id"], "101")

    def test_blocks_unapproved_piece(self) -> None:
        publisher = _FakePublisher()
        audit: list[AuditEvent] = []

        with self.assertRaises(ApprovalRequired):
            publish_content(
                publisher, _piece("pending_approval"),
                autonomy_mode="review", actor="founder@x.com", audit_log=audit,
            )

        self.assertEqual(publisher.calls, [])  # nothing published
        self.assertEqual(audit, [])  # nothing audited

    def test_blocks_non_review_autonomy(self) -> None:
        publisher = _FakePublisher()
        with self.assertRaises(ApprovalRequired):
            publish_content(
                publisher, _piece("approved"),
                autonomy_mode="auto_publish", actor="x", audit_log=[],
            )
        self.assertEqual(publisher.calls, [])


if __name__ == "__main__":
    unittest.main()
