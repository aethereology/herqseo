"""Thin FastAPI adapter over LoopService — the TS<->Python boundary (D11).

Optional: requires the ``api`` extra (fastapi + uvicorn). This module is NOT
imported by the package or the test suite, so CI stays offline. Run with::

    pip install -e ".[api,openai,crawl]"
    uvicorn queryclear_agent_runtime.app:build_app --factory
"""
from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from .content import ApprovalRequired, ContentPiece
from .monitoring import Opportunity
from .service import LoopError, LoopService


class RunRequest(BaseModel):
    org_id: str
    domain_id: str
    domain_url: str
    brand: str
    samples: int = 3


class ReviewRequest(BaseModel):
    approved: bool
    reviewer: str
    note: str | None = None


class PublishRequest(BaseModel):
    actor: str


def _piece_json(piece: ContentPiece) -> dict[str, Any]:
    return {
        "id": piece.id,
        "opportunity_id": piece.opportunity_id,
        "title": piece.title,
        "body": piece.body,
        "status": piece.status,
        "reviewer": piece.reviewer,
        "cms_post_id": piece.cms_post_id,
        "published_at": piece.published_at,
        "cost_usd": str(piece.cost_usd),
    }


def _opportunity_json(opp: Opportunity) -> dict[str, Any]:
    return {
        "id": opp.id,
        "type": opp.opportunity_type,
        "title": opp.title,
        "rationale": opp.rationale,
        "priority": opp.priority,
        "status": opp.status,
    }


def create_app(service: LoopService) -> FastAPI:
    app = FastAPI(title="QueryClear Agent Runtime (M0)")

    @app.post("/runs")
    def create_run(req: RunRequest) -> dict[str, Any]:
        summary = service.run(
            org_id=req.org_id, domain_id=req.domain_id,
            domain_url=req.domain_url, brand=req.brand, samples=req.samples,
        )
        return {
            "run_id": summary.run_id,
            "opportunities": [_opportunity_json(o) for o in summary.opportunities],
            "draft": _piece_json(summary.draft) if summary.draft else None,
        }

    @app.get("/drafts/{draft_id}")
    def get_draft(draft_id: str) -> dict[str, Any]:
        try:
            return _piece_json(service.get_draft(draft_id))
        except LoopError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post("/drafts/{draft_id}/review")
    def review(draft_id: str, req: ReviewRequest) -> dict[str, Any]:
        try:
            piece = service.review(
                draft_id, approved=req.approved, reviewer=req.reviewer, note=req.note
            )
        except LoopError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return _piece_json(piece)

    @app.post("/drafts/{draft_id}/publish")
    def publish(draft_id: str, req: PublishRequest) -> dict[str, Any]:
        try:
            outcome = service.publish(draft_id, actor=req.actor)
        except ApprovalRequired as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except LoopError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return {
            "piece": _piece_json(outcome.piece),
            "cms_post_id": outcome.result.cms_post_id,
            "url": outcome.result.url,
            "status": outcome.result.status,
        }

    @app.get("/audit")
    def audit() -> list[dict[str, Any]]:
        return [
            {
                "entity_id": e.entity_id,
                "action": e.action,
                "actor": e.actor,
                "created_at": e.created_at,
                "metadata": e.metadata,
            }
            for e in service.audit_log
        ]

    return app
