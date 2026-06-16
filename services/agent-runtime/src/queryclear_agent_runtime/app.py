"""Thin FastAPI adapter over LoopService — the TS<->Python boundary (D11).

Optional: requires the ``api`` extra (fastapi + uvicorn). This module is NOT
imported by the package or the test suite, so CI stays offline. Run with::

    pip install -e ".[api,openai,crawl]"
    uvicorn queryclear_agent_runtime.app:build_app --factory
"""
from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from .audit import AuditReport
from .content import ApprovalRequired, ContentPiece
from .monitoring import Opportunity
from .service import LoopError, LoopService


class RunRequest(BaseModel):
    org_id: str
    domain_id: str
    domain_url: str
    brand: str
    brand_voice: str | None = None
    samples: int = 3


class ReviewRequest(BaseModel):
    org_id: str
    approved: bool
    reviewer: str
    note: str | None = None


class PublishRequest(BaseModel):
    org_id: str
    actor: str


class AuditRequest(BaseModel):
    org_id: str
    domain_id: str
    domain_url: str
    brand: str | None = None
    samples: int = 3


def _brand_from_url(domain_url: str) -> str:
    host = urlparse(domain_url).netloc or domain_url
    name = host.split(":")[0].removeprefix("www.").split(".")[0]
    return name.replace("-", " ").title() or domain_url


def _report_json(report: AuditReport) -> dict[str, Any]:
    return {
        "domain_url": report.domain_url,
        "page_title": report.page_title,
        "findings": [
            {
                "code": f.code,
                "severity": f.severity,
                "title": f.title,
                "detail": f.detail,
                "recommendation": f.recommendation,
                "url": f.url,
            }
            for f in report.findings
        ],
        "queries": [
            {
                "query": c.query,
                "cited_count": c.cited_count,
                "samples": c.samples,
                "citation_frequency": c.citation_frequency,
            }
            for c in report.checks
        ],
        "opportunities": [_opportunity_json(o) for o in report.opportunities],
        "sample_draft": _piece_json(report.sample_draft) if report.sample_draft else None,
    }


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
            domain_url=req.domain_url, brand=req.brand,
            brand_voice=req.brand_voice, samples=req.samples,
        )
        return {
            "run_id": summary.run_id,
            "opportunities": [_opportunity_json(o) for o in summary.opportunities],
            "draft": _piece_json(summary.draft) if summary.draft else None,
        }

    @app.get("/drafts/{draft_id}")
    def get_draft(draft_id: str, org_id: str) -> dict[str, Any]:
        try:
            return _piece_json(service.get_draft(draft_id, org_id=org_id))
        except LoopError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post("/drafts/{draft_id}/review")
    def review(draft_id: str, req: ReviewRequest) -> dict[str, Any]:
        try:
            piece = service.review(
                draft_id, org_id=req.org_id, approved=req.approved,
                reviewer=req.reviewer, note=req.note,
            )
        except LoopError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return _piece_json(piece)

    @app.post("/drafts/{draft_id}/publish")
    def publish(draft_id: str, req: PublishRequest) -> dict[str, Any]:
        try:
            outcome = service.publish(draft_id, org_id=req.org_id, actor=req.actor)
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

    @app.post("/audit")
    def run_audit(req: AuditRequest) -> dict[str, Any]:
        report = service.audit(
            req.domain_url,
            req.brand or _brand_from_url(req.domain_url),
            org_id=req.org_id,
            domain_id=req.domain_id,
            samples=req.samples,
        )
        return _report_json(report)

    @app.get("/audit-log")
    def audit_log(org_id: str) -> list[dict[str, Any]]:
        return [
            {
                "entity_id": e.entity_id,
                "action": e.action,
                "actor": e.actor,
                "created_at": e.created_at,
                "metadata": e.metadata,
            }
            for e in service.audit_events.list(org_id=org_id)
        ]

    return app
