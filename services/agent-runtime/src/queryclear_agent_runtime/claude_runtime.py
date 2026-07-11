"""ClaudeAgentRuntime — the first real ``AgentRuntime`` implementation (D14).

One Claude Agent SDK session per operator run. Framework specifics stay inside
this module (D7): product code depends only on the ``AgentRuntime`` interface,
and the SDK is lazily imported (``agent`` extra) so core + CI never need it —
tests and demo mode inject a fake ``session_runner`` instead.

Guardrails:
- The agent gets exactly three tools (run the loop, read history, write a
  report). There is NO publish tool and no built-in tools, so publishing stays
  behind the human review endpoints; ``ApprovalRequired`` is the backstop.
- The whole session is metered as ONE ``TokenMeter.run_metered`` call
  (``task_class="agent_run"``): the reservation rejects the run up front if the
  org can't afford it, and the settle records the SDK-reported usage. Model
  calls the loop makes inside tools meter themselves as they always have.
- The loop tool is pinned to the task payload's domain/brand — the agent
  decides WHETHER to run, never WHICH domain to hit.
"""
from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import uuid4

from .metering import ModelRequest, ModelResponse, TokenMeter
from .runtime import (
    AgentHandle,
    AgentNotFound,
    AgentRuntime,
    AgentStatus,
    AgentTask,
    RunResult,
)
from .service import LoopService

AGENT_TOOL_NAMES = ("run_operator_loop", "get_recent_results", "write_run_report")

_SYSTEM_PROMPT = (
    "You are the QueryClear operator agent for one brand. Your job is one "
    "operator run: review what previous runs produced, decide whether to run "
    "the optimization loop now, and finish by writing a short run report. "
    "You can only use the provided queryclear tools. You cannot publish "
    "anything — drafts always wait for human review."
)


@dataclass
class _RunCollector:
    """What the tools actually did during one session — the ground truth the
    RunResult is built from (never the model's own claims)."""

    opportunity_ids: list[str] = field(default_factory=list)
    draft_ids: list[str] = field(default_factory=list)
    report: str | None = None
    learnings: str | None = None


@dataclass(frozen=True)
class AgentRunContext:
    """Everything a session runner needs. The production runner turns ``tools``
    into SDK tools; test/demo runners call them directly."""

    handle: AgentHandle
    task: AgentTask
    system_prompt: str
    user_prompt: str
    model: str
    max_turns: int
    tools: dict[str, Callable[..., dict[str, Any]]]


SessionRunner = Callable[[AgentRunContext], ModelResponse]


class ClaudeAgentRuntime(AgentRuntime):
    """Claude Agent SDK boundary; framework calls stay behind this class."""

    def __init__(
        self,
        service: LoopService,
        meter: TokenMeter,
        *,
        model: str = "claude-sonnet-4-6",
        max_turns: int = 12,
        reserve_input_tokens: int = 150_000,
        reserve_output_tokens: int = 50_000,
        session_runner: SessionRunner | None = None,
    ) -> None:
        self._service = service
        self._meter = meter
        self._model = model
        self._max_turns = max_turns
        self._reserve_input_tokens = reserve_input_tokens
        self._reserve_output_tokens = reserve_output_tokens
        self._session_runner = session_runner or _sdk_session_runner
        self._handles: dict[str, AgentHandle] = {}
        self._domain_index: dict[tuple[str, str], str] = {}
        self._memory: dict[str, dict[str, Any]] = {}
        self._schedules: dict[str, str] = {}
        self._runs: dict[str, list[RunResult]] = {}

    def provision(self, org_id: str, domain_id: str) -> AgentHandle:
        existing_id = self._domain_index.get((org_id, domain_id))
        if existing_id is not None:
            handle = self._handles.get(existing_id)
            if handle is not None:
                return handle

        handle = AgentHandle(
            agent_id=str(uuid4()),
            org_id=org_id,
            domain_id=domain_id,
            status=AgentStatus.ACTIVE,
            memory_store_ref=f"memory://{org_id}/{domain_id}",
        )
        self._handles[handle.agent_id] = handle
        self._domain_index[(org_id, domain_id)] = handle.agent_id
        self._memory[handle.agent_id] = {
            "brand_profile": {},
            "site_map": {},
            "action_history": [],
        }
        self._runs[handle.agent_id] = []
        return handle

    def get(self, agent_id: str) -> AgentHandle | None:
        return self._handles.get(agent_id)

    def list(
        self, *, org_id: str | None = None, domain_id: str | None = None
    ) -> tuple[AgentHandle, ...]:
        handles = self._handles.values()
        if org_id is not None:
            handles = (h for h in handles if h.org_id == org_id)
        if domain_id is not None:
            handles = (h for h in handles if h.domain_id == domain_id)
        return tuple(sorted(handles, key=lambda h: (h.org_id, h.domain_id, h.agent_id)))

    def run(self, handle: AgentHandle, task: AgentTask) -> RunResult:
        current = self._require_handle(handle.agent_id)
        if self.status(handle) == AgentStatus.PAUSED:
            result = self._result(current, task, status="failed", collector=_RunCollector())
            self._runs[current.agent_id].append(result)
            return result

        collector = _RunCollector()
        context = AgentRunContext(
            handle=current,
            task=task,
            system_prompt=self._system_prompt(current),
            user_prompt=self._user_prompt(current, task),
            model=self._model,
            max_turns=self._max_turns,
            tools=self._build_tools(current, task, collector),
        )
        request = ModelRequest(
            org_id=current.org_id,
            domain_id=current.domain_id,
            task_class="agent_run",
            provider="anthropic",
            model=self._model,
            estimated_input_tokens=self._reserve_input_tokens,
            max_output_tokens=self._reserve_output_tokens,
        )
        # BudgetExceeded propagates: an unaffordable run must fail loudly, before
        # the session spends anything.
        state = self._meter.run_metered(request, lambda: self._session_runner(context))

        result_status = "needs_approval" if task.autonomy_mode == "review" else "completed"
        result = self._result(
            current,
            task,
            status=result_status,
            collector=collector,
            usage_record_ids=[state.usage.id],
        )
        self._runs[current.agent_id].append(result)
        self._append_action_history(current.agent_id, task, result, collector)
        return result

    def get_memory(self, handle: AgentHandle) -> dict[str, Any]:
        self._require_handle(handle.agent_id)
        return dict(self._memory.get(handle.agent_id, {}))

    def set_memory(self, handle: AgentHandle, memory: dict[str, Any]) -> None:
        self._require_handle(handle.agent_id)
        self._memory[handle.agent_id] = dict(memory)

    def schedule(self, handle: AgentHandle, cadence: str) -> None:
        self._require_handle(handle.agent_id)
        if not cadence.strip():
            raise ValueError("cadence must be non-empty")
        self._schedules[handle.agent_id] = cadence

    def schedule_for(self, handle: AgentHandle) -> str | None:
        self._require_handle(handle.agent_id)
        return self._schedules.get(handle.agent_id)

    def results(self, handle: AgentHandle) -> tuple[RunResult, ...]:
        self._require_handle(handle.agent_id)
        return tuple(self._runs.get(handle.agent_id, ()))

    def pause(self, handle: AgentHandle) -> AgentHandle:
        self._require_handle(handle.agent_id)
        return self._replace_status(handle, AgentStatus.PAUSED)

    def resume(self, handle: AgentHandle) -> AgentHandle:
        self._require_handle(handle.agent_id)
        return self._replace_status(handle, AgentStatus.ACTIVE)

    def status(self, handle: AgentHandle) -> AgentStatus:
        current = self._require_handle(handle.agent_id)
        return current.status

    def _build_tools(
        self, handle: AgentHandle, task: AgentTask, collector: _RunCollector
    ) -> dict[str, Callable[..., dict[str, Any]]]:
        domain_url = task.payload.get("domain_url")
        brand = task.payload.get("brand")

        def run_operator_loop() -> dict[str, Any]:
            if not isinstance(domain_url, str) or not isinstance(brand, str):
                return {"error": "task payload must include domain_url and brand"}
            summary = self._service.run(
                org_id=handle.org_id,
                domain_id=handle.domain_id,
                domain_url=domain_url,
                brand=brand,
            )
            collector.opportunity_ids.extend(o.id for o in summary.opportunities)
            if summary.draft is not None:
                collector.draft_ids.append(summary.draft.id)
            return {
                "run_id": summary.run_id,
                "opportunities": [
                    {"id": o.id, "title": o.title, "priority": o.priority}
                    for o in summary.opportunities
                ],
                "draft": (
                    {
                        "id": summary.draft.id,
                        "title": summary.draft.title,
                        "status": summary.draft.status,
                    }
                    if summary.draft is not None
                    else None
                ),
            }

        def get_recent_results() -> dict[str, Any]:
            memory = self._memory.get(handle.agent_id, {})
            recent = self._runs.get(handle.agent_id, [])[-5:]
            return {
                "runs": [
                    {
                        "run_id": r.run_id,
                        "status": r.status,
                        "opportunity_ids": r.opportunity_ids,
                        "draft_ids": r.draft_ids,
                        "created_at": r.created_at.isoformat(),
                    }
                    for r in recent
                ],
                "action_history": list(memory.get("action_history", []))[-10:],
                "learnings": list(memory.get("learnings", []))[-10:],
            }

        def write_run_report(summary: str, learnings: str = "") -> dict[str, Any]:
            collector.report = summary
            collector.learnings = learnings or None
            return {"ok": True}

        return {
            "run_operator_loop": run_operator_loop,
            "get_recent_results": get_recent_results,
            "write_run_report": write_run_report,
        }

    def _system_prompt(self, handle: AgentHandle) -> str:
        memory = self._memory.get(handle.agent_id, {})
        return (
            f"{_SYSTEM_PROMPT}\n\nAgent memory (brand profile and learnings):\n"
            f"{json.dumps({k: v for k, v in memory.items() if k != 'action_history'}, default=str)}"
        )

    def _user_prompt(self, handle: AgentHandle, task: AgentTask) -> str:
        return (
            f"Run one operator cycle for brand {task.payload.get('brand')!r} at "
            f"{task.payload.get('domain_url')!r} (org {handle.org_id}, domain "
            f"{handle.domain_id}). First call get_recent_results, then decide "
            "whether to call run_operator_loop, and always finish with "
            "write_run_report (summary + what you learned)."
        )

    def _replace_status(self, handle: AgentHandle, status: AgentStatus) -> AgentHandle:
        current = self._require_handle(handle.agent_id)
        updated = AgentHandle(
            agent_id=current.agent_id,
            org_id=current.org_id,
            domain_id=current.domain_id,
            status=status,
            memory_store_ref=current.memory_store_ref,
        )
        self._handles[handle.agent_id] = updated
        return updated

    def _require_handle(self, agent_id: str) -> AgentHandle:
        handle = self._handles.get(agent_id)
        if handle is None:
            raise AgentNotFound(f"unknown agent {agent_id!r}")
        return handle

    def _result(
        self,
        handle: AgentHandle,
        task: AgentTask,
        *,
        status: str,
        collector: _RunCollector,
        usage_record_ids: list[str] | None = None,
    ) -> RunResult:
        return RunResult(
            run_id=str(uuid4()),
            agent_id=handle.agent_id,
            org_id=handle.org_id,
            domain_id=handle.domain_id,
            task_class=task.task_class,
            status=status,
            opportunity_ids=list(collector.opportunity_ids),
            draft_ids=list(collector.draft_ids),
            usage_record_ids=list(usage_record_ids or []),
            created_at=datetime.now(UTC),
        )

    def _append_action_history(
        self, agent_id: str, task: AgentTask, result: RunResult, collector: _RunCollector
    ) -> None:
        memory = dict(self._memory.get(agent_id, {}))
        history = list(memory.get("action_history", []))
        history.append(
            {
                "run_id": result.run_id,
                "task_class": task.task_class,
                "status": result.status,
                "created_at": result.created_at.isoformat(),
                "dry_run": task.dry_run,
                "report": collector.report,
            }
        )
        memory["action_history"] = history
        if collector.learnings:
            learnings = list(memory.get("learnings", []))
            learnings.append(collector.learnings)
            memory["learnings"] = learnings
        self._memory[agent_id] = memory


def demo_session_runner(context: AgentRunContext) -> ModelResponse:
    """Offline stand-in (no SDK, no key): scripts the canonical session —
    check history, run the loop, write a report. Used by serve.py demo mode."""
    context.tools["get_recent_results"]()
    loop = context.tools["run_operator_loop"]()
    draft = loop.get("draft") if isinstance(loop, dict) else None
    context.tools["write_run_report"](
        summary=(
            f"Demo operator run: {len(loop.get('opportunities', []))} opportunities, "
            f"draft {'created' if draft else 'not needed'}."
            if isinstance(loop, dict) and "error" not in loop
            else f"Demo operator run skipped the loop: {loop.get('error')}"
        ),
        learnings="Offline demo session (no ANTHROPIC_API_KEY set).",
    )
    return ModelResponse(
        content="demo agent run", input_tokens=500, output_tokens=300, cost_usd=Decimal("0.0050")
    )


def _sdk_session_runner(context: AgentRunContext) -> ModelResponse:
    """Production runner: one Claude Agent SDK session. Lazily imported so the
    core package never needs the ``agent`` extra."""
    import asyncio

    return asyncio.run(_run_sdk_session(context))


async def _run_sdk_session(context: AgentRunContext) -> ModelResponse:
    import asyncio

    from claude_agent_sdk import (
        ClaudeAgentOptions,
        create_sdk_mcp_server,
        query,
        tool,
    )

    def wrap(name: str, description: str, schema: dict[str, Any]):
        fn = context.tools[name]

        @tool(name, description, schema)
        async def _tool(args: dict[str, Any]) -> dict[str, Any]:
            result = await asyncio.to_thread(lambda: fn(**args))
            return {"content": [{"type": "text", "text": json.dumps(result, default=str)}]}

        return _tool

    sdk_tools = [
        wrap(
            "run_operator_loop",
            "Run one full operator loop (crawl, AI-visibility monitoring, one "
            "content draft) for this agent's configured domain. Takes no "
            "arguments — the domain and brand are fixed by the task.",
            {},
        ),
        wrap(
            "get_recent_results",
            "Recent run results, action history, and learnings for this agent.",
            {},
        ),
        wrap(
            "write_run_report",
            "Finish the run: record a short summary and what you learned.",
            {"summary": str, "learnings": str},
        ),
    ]
    options = ClaudeAgentOptions(
        system_prompt=context.system_prompt,
        model=context.model,
        max_turns=context.max_turns,
        mcp_servers={"queryclear": create_sdk_mcp_server(name="queryclear", tools=sdk_tools)},
        # Whitelist ONLY our three tools — no Bash/Write/WebFetch, and no
        # publish surface at all.
        allowed_tools=[f"mcp__queryclear__{name}" for name in AGENT_TOOL_NAMES],
        disallowed_tools=["Bash", "Read", "Write", "Edit", "Glob", "Grep", "WebFetch", "WebSearch", "Task", "NotebookEdit"],
    )

    result_message: Any = None
    async for message in query(prompt=context.user_prompt, options=options):
        if type(message).__name__ == "ResultMessage":
            result_message = message

    if result_message is None:
        raise RuntimeError("Claude Agent SDK session ended without a result message")

    usage = getattr(result_message, "usage", None) or {}
    input_tokens = int(usage.get("input_tokens", 0)) + int(
        usage.get("cache_creation_input_tokens", 0)
    )
    output_tokens = int(usage.get("output_tokens", 0))
    total_cost = getattr(result_message, "total_cost_usd", None)
    return ModelResponse(
        content=str(getattr(result_message, "result", "") or ""),
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_usd=Decimal(str(total_cost)) if total_cost is not None else Decimal("0"),
    )
