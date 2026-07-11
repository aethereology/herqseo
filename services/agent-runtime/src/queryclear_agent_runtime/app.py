"""Thin FastAPI adapter over LoopService — the TS<->Python boundary (D11).

Optional: requires the ``api`` extra (fastapi + uvicorn). This module is NOT
imported by the package or the test suite, so CI stays offline. Run with::

    pip install -e ".[api,openai,crawl]"
    uvicorn queryclear_agent_runtime.app:build_app --factory
"""
from __future__ import annotations

from collections.abc import Callable
from typing import Any
from urllib.parse import urlparse

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from .audit import AuditReport
from .claude_runtime import ClaudeAgentRuntime
from .content import ApprovalRequired, ContentPiece
from .credentials import WordPressCredentials
from .metering import BudgetExceeded
from .monitoring import Opportunity
from .publishing import PreflightError, WordPressPublisher
from .repositories import CmsCredentialRepository
from .runtime import AgentHandle, AgentNotFound, AgentRuntime, AgentTask, RunResult
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


class ProvisionAgentRequest(BaseModel):
    org_id: str
    domain_id: str


class AgentRunRequest(BaseModel):
    task_class: str
    autonomy_mode: str = "review"
    dry_run: bool = True
    payload: dict[str, Any] | None = None


class SetMemoryRequest(BaseModel):
    memory: dict[str, Any]


class ScheduleRequest(BaseModel):
    cadence: str


class WordPressPreflightRequest(BaseModel):
    base_url: str
    username: str
    app_password: str


class WordPressConnectRequest(WordPressPreflightRequest):
    org_id: str
    domain_id: str


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
                "engine": c.engine,
                "query": c.query,
                "cited_count": c.cited_count,
                "samples": c.samples,
                "citation_frequency": c.citation_frequency,
                "confidence_low": c.citation_confidence_interval[0],
                "confidence_high": c.citation_confidence_interval[1],
                "measured": c.measured,
            }
            for c in report.checks
        ],
        "opportunities": [_opportunity_json(o) for o in report.opportunities],
        "recommendations": [
            {
                "rank": r.rank,
                "priority": r.priority,
                "kind": r.kind,
                "title": r.title,
                "rationale": r.rationale,
                "action": r.action,
                "provenance": r.provenance,
                "evidence": r.evidence,
            }
            for r in report.recommendations
        ],
        "sample_draft": _piece_json(report.sample_draft) if report.sample_draft else None,
        "detected_voice": report.detected_voice,
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


def _agent_json(handle: AgentHandle) -> dict[str, Any]:
    return {
        "agent_id": handle.agent_id,
        "org_id": handle.org_id,
        "domain_id": handle.domain_id,
        "status": handle.status.value,
        "memory_store_ref": handle.memory_store_ref,
    }


def _run_result_json(result: RunResult) -> dict[str, Any]:
    return {
        "run_id": result.run_id,
        "agent_id": result.agent_id,
        "org_id": result.org_id,
        "domain_id": result.domain_id,
        "task_class": result.task_class,
        "status": result.status,
        "opportunity_ids": result.opportunity_ids,
        "draft_ids": result.draft_ids,
        "usage_record_ids": result.usage_record_ids,
        "created_at": result.created_at.isoformat(),
    }


def create_app(
    service: LoopService,
    agent_runtime: AgentRuntime | None = None,
    wordpress_publisher_factory: Callable[..., WordPressPublisher] = WordPressPublisher,
    cms_credentials: CmsCredentialRepository | None = None,
) -> FastAPI:
    app = FastAPI(title="QueryClear Agent Runtime (M0)")
    agents = agent_runtime or ClaudeAgentRuntime(service, service.meter)
    credential_store = cms_credentials or service.cms_credentials

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

    @app.post("/integrations/wordpress/preflight")
    def wordpress_preflight(req: WordPressPreflightRequest) -> dict[str, Any]:
        publisher = wordpress_publisher_factory(
            base_url=req.base_url,
            username=req.username,
            app_password=req.app_password,
        )
        try:
            publisher.preflight()
        except PreflightError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {
            "ok": True,
            "message": "WordPress REST API is reachable and credentials are valid.",
        }

    @app.post("/integrations/wordpress/connect")
    def wordpress_connect(req: WordPressConnectRequest) -> dict[str, Any]:
        publisher = wordpress_publisher_factory(
            base_url=req.base_url,
            username=req.username,
            app_password=req.app_password,
        )
        try:
            publisher.preflight()
        except PreflightError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        ref = credential_store.save_wordpress(
            WordPressCredentials(
                base_url=req.base_url,
                username=req.username,
                app_password=req.app_password,
            ),
            org_id=req.org_id,
            domain_id=req.domain_id,
        )
        return {
            "ok": True,
            "credentials_ref": ref,
            "base_url": req.base_url,
            "username": req.username,
            "message": "WordPress credentials are connected and saved.",
        }

    @app.get("/integrations/wordpress/status")
    def wordpress_status(org_id: str, domain_id: str) -> dict[str, Any]:
        credentials = credential_store.get_wordpress_for_domain(
            org_id=org_id, domain_id=domain_id
        )
        if credentials is None:
            return {"connected": False}
        return {
            "connected": True,
            "base_url": credentials.base_url,
            "username": credentials.username,
        }

    @app.post("/agents")
    def provision_agent(req: ProvisionAgentRequest) -> dict[str, Any]:
        return _agent_json(agents.provision(req.org_id, req.domain_id))

    @app.get("/agents")
    def list_agents(
        org_id: str | None = None, domain_id: str | None = None
    ) -> list[dict[str, Any]]:
        return [_agent_json(handle) for handle in agents.list(org_id=org_id, domain_id=domain_id)]

    @app.get("/agents/{agent_id}/status")
    def agent_status(agent_id: str) -> dict[str, Any]:
        handle = agents.get(agent_id)
        if handle is None:
            raise HTTPException(status_code=404, detail=f"unknown agent {agent_id!r}")
        return _agent_json(handle)

    @app.post("/agents/{agent_id}/run")
    def run_agent(agent_id: str, req: AgentRunRequest) -> dict[str, Any]:
        handle = agents.get(agent_id)
        if handle is None:
            raise HTTPException(status_code=404, detail=f"unknown agent {agent_id!r}")
        try:
            result = agents.run(
                handle,
                AgentTask(
                    task_class=req.task_class,
                    autonomy_mode=req.autonomy_mode,
                    dry_run=req.dry_run,
                    payload=req.payload or {},
                ),
            )
        except AgentNotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except BudgetExceeded as exc:
            raise HTTPException(status_code=402, detail=str(exc)) from exc
        return _run_result_json(result)

    @app.get("/agents/{agent_id}/results")
    def agent_results(agent_id: str) -> list[dict[str, Any]]:
        handle = agents.get(agent_id)
        if handle is None:
            raise HTTPException(status_code=404, detail=f"unknown agent {agent_id!r}")
        return [_run_result_json(result) for result in agents.results(handle)]

    @app.get("/agents/{agent_id}/memory")
    def get_agent_memory(agent_id: str) -> dict[str, Any]:
        handle = agents.get(agent_id)
        if handle is None:
            raise HTTPException(status_code=404, detail=f"unknown agent {agent_id!r}")
        try:
            return agents.get_memory(handle)
        except AgentNotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.put("/agents/{agent_id}/memory")
    def set_agent_memory(agent_id: str, req: SetMemoryRequest) -> dict[str, Any]:
        handle = agents.get(agent_id)
        if handle is None:
            raise HTTPException(status_code=404, detail=f"unknown agent {agent_id!r}")
        try:
            agents.set_memory(handle, req.memory)
            return agents.get_memory(handle)
        except AgentNotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post("/agents/{agent_id}/schedule")
    def schedule_agent(agent_id: str, req: ScheduleRequest) -> dict[str, Any]:
        handle = agents.get(agent_id)
        if handle is None:
            raise HTTPException(status_code=404, detail=f"unknown agent {agent_id!r}")
        try:
            agents.schedule(handle, req.cadence)
        except AgentNotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return {"agent_id": agent_id, "cadence": req.cadence}

    @app.post("/agents/{agent_id}/pause")
    def pause_agent(agent_id: str) -> dict[str, Any]:
        handle = agents.get(agent_id)
        if handle is None:
            raise HTTPException(status_code=404, detail=f"unknown agent {agent_id!r}")
        try:
            return _agent_json(agents.pause(handle))
        except AgentNotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post("/agents/{agent_id}/resume")
    def resume_agent(agent_id: str) -> dict[str, Any]:
        handle = agents.get(agent_id)
        if handle is None:
            raise HTTPException(status_code=404, detail=f"unknown agent {agent_id!r}")
        try:
            return _agent_json(agents.resume(handle))
        except AgentNotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    return app
