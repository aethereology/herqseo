from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from typing import Protocol

from .content import ContentPiece, assert_approved_for_publish

# M0 (D9): publish to staging/draft only — NEVER a customer's live page.
# WordPress statuses that are not publicly live:
_STAGING_STATUSES = frozenset({"draft", "pending"})


class StagingOnlyError(RuntimeError):
    pass


class PreflightError(RuntimeError):
    """A WordPress connection check failed, with an actionable reason."""


@dataclass(frozen=True)
class PublishResult:
    cms_post_id: str
    url: str
    status: str


@dataclass(frozen=True)
class AuditEvent:
    entity_type: str
    entity_id: str
    action: str
    actor: str
    created_at: str
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class PublishOutcome:
    piece: ContentPiece
    result: PublishResult
    event: AuditEvent


class CmsPublisher(Protocol):
    def publish(self, *, title: str, body: str, status: str = "draft") -> PublishResult:
        ...


class WordPressPublisher:
    """WordPress REST connector (Phase 1, first CMS). ``httpx`` is imported lazily
    so the package stays importable without the dependency (tests inject a client).

    M0 publishes drafts only; live publishing is refused at this layer.
    """

    def __init__(
        self,
        *,
        base_url: str,
        username: str,
        app_password: str,
        client: object | None = None,
        timeout: float = 15.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._auth = (username, app_password)
        self._client = client
        self._timeout = timeout

    def preflight(self) -> None:
        """Verify, before we rely on it to publish, that the REST API is reachable,
        returns JSON (pretty permalinks are on), and accepts the application
        password. Raises ``PreflightError`` with a fix-oriented message; returns
        ``None`` on success.

        Both failure modes here are real onboarding traps: with plain permalinks
        ``/wp-json/`` silently serves the HTML home page (HTTP 200), and WordPress
        only honors application passwords over HTTPS or on a ``local`` environment.
        """
        client = self._get_client()
        url = f"{self._base_url}/wp-json/wp/v2/users/me?context=edit"
        try:
            response = client.get(url, auth=self._auth, timeout=self._timeout)
        except Exception as exc:  # DNS / connection / TLS
            raise PreflightError(
                f"Could not reach {self._base_url}. Check the site URL and that the "
                f"site is online ({exc})."
            ) from exc

        status = getattr(response, "status_code", None)
        if status in (401, 403):
            raise PreflightError(
                f"WordPress rejected the credentials (HTTP {status}). Verify the "
                "username and application password, and note that WordPress only "
                "accepts application passwords over HTTPS or on a 'local' environment."
            )
        content_type = response.headers.get("content-type", "")
        if "json" not in content_type.lower():
            raise PreflightError(
                f"The REST API did not return JSON (content-type: {content_type!r}). "
                "The site is most likely using plain permalinks — switch to pretty "
                "permalinks (Settings → Permalinks) so /wp-json/ reaches the REST API."
            )
        if status is not None and status >= 400:
            raise PreflightError(f"WordPress REST preflight failed (HTTP {status}).")

    def publish(self, *, title: str, body: str, status: str = "draft") -> PublishResult:
        if status not in _STAGING_STATUSES:
            raise StagingOnlyError(
                f"refusing to publish with status {status!r}; M0 allows only "
                f"{sorted(_STAGING_STATUSES)} (no live-site writes)"
            )
        client = self._get_client()
        response = client.post(
            f"{self._base_url}/wp-json/wp/v2/posts",
            json={"title": title, "content": body, "status": status},
            auth=self._auth,
            timeout=self._timeout,
        )
        response.raise_for_status()
        data = response.json()
        return PublishResult(
            cms_post_id=str(data["id"]),
            url=data.get("link", ""),
            status=data.get("status", status),
        )

    def _get_client(self):  # type: ignore[no-untyped-def]
        if self._client is None:
            import httpx  # lazy: optional dependency

            self._client = httpx.Client()
        return self._client


def publish_content(
    publisher: CmsPublisher,
    piece: ContentPiece,
    *,
    autonomy_mode: str,
    actor: str,
    audit_log: list[AuditEvent],
) -> PublishOutcome:
    """Publish an approved piece to staging/draft and append an audit event.

    The approval gate runs first: nothing reaches the CMS without a human
    approval in Review mode (M0). The audit event links the publish to the
    approver and the metered model call behind the draft.
    """
    assert_approved_for_publish(piece, autonomy_mode)

    result = publisher.publish(title=piece.title, body=piece.body, status="draft")
    now = datetime.now(UTC).isoformat()

    published = replace(
        piece, status="published", cms_post_id=result.cms_post_id, published_at=now
    )
    event = AuditEvent(
        entity_type="content_piece",
        entity_id=piece.id,
        action="publish",
        actor=actor,
        created_at=now,
        metadata={
            "cms_post_id": result.cms_post_id,
            "cms_url": result.url,
            "cms_status": result.status,
            "approved_by": piece.reviewer,
            "usage_record_id": piece.usage_record_id,
        },
    )
    audit_log.append(event)
    return PublishOutcome(piece=published, result=result, event=event)
