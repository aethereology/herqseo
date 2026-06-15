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
