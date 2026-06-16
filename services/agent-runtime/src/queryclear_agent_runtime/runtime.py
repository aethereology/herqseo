from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4


class AgentNotFound(RuntimeError):
    pass


class AgentStatus(StrEnum):
    PROVISIONING = "provisioning"
    ACTIVE = "active"
    PAUSED = "paused"
    FAILED = "failed"


@dataclass(frozen=True)
class AgentHandle:
    agent_id: str
    org_id: str
    domain_id: str
    status: AgentStatus
    memory_store_ref: str


@dataclass(frozen=True)
class AgentTask:
    task_class: str
    autonomy_mode: str
    dry_run: bool = True
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RunResult:
    run_id: str
    agent_id: str
    org_id: str
    domain_id: str
    task_class: str
    status: str
    opportunity_ids: list[str]
    draft_ids: list[str]
    usage_record_ids: list[str]
    created_at: datetime


class AgentRuntime(ABC):
    @abstractmethod
    def provision(self, org_id: str, domain_id: str) -> AgentHandle:
        raise NotImplementedError

    @abstractmethod
    def get(self, agent_id: str) -> AgentHandle | None:
        raise NotImplementedError

    @abstractmethod
    def list(
        self, *, org_id: str | None = None, domain_id: str | None = None
    ) -> tuple[AgentHandle, ...]:
        raise NotImplementedError

    @abstractmethod
    def run(self, handle: AgentHandle, task: AgentTask) -> RunResult:
        raise NotImplementedError

    @abstractmethod
    def get_memory(self, handle: AgentHandle) -> dict[str, object]:
        raise NotImplementedError

    @abstractmethod
    def set_memory(self, handle: AgentHandle, memory: dict[str, object]) -> None:
        raise NotImplementedError

    @abstractmethod
    def schedule(self, handle: AgentHandle, cadence: str) -> None:
        raise NotImplementedError

    @abstractmethod
    def schedule_for(self, handle: AgentHandle) -> str | None:
        raise NotImplementedError

    @abstractmethod
    def results(self, handle: AgentHandle) -> tuple[RunResult, ...]:
        raise NotImplementedError

    @abstractmethod
    def pause(self, handle: AgentHandle) -> AgentHandle:
        raise NotImplementedError

    @abstractmethod
    def resume(self, handle: AgentHandle) -> AgentHandle:
        raise NotImplementedError

    @abstractmethod
    def status(self, handle: AgentHandle) -> AgentStatus:
        raise NotImplementedError


class HermesAgentRuntime(AgentRuntime):
    """Hermes boundary placeholder; framework calls stay behind this class."""

    def __init__(self) -> None:
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
            result = self._result(current, task, status="failed")
            self._runs[current.agent_id].append(result)
            return result

        result_status = "needs_approval" if task.autonomy_mode == "review" else "completed"
        result = self._result(current, task, status=result_status)
        self._runs[current.agent_id].append(result)
        self._append_action_history(current.agent_id, task, result)
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

    def pause(self, handle: AgentHandle) -> AgentHandle:
        self._require_handle(handle.agent_id)
        return self._replace_status(handle, AgentStatus.PAUSED)

    def resume(self, handle: AgentHandle) -> AgentHandle:
        self._require_handle(handle.agent_id)
        return self._replace_status(handle, AgentStatus.ACTIVE)

    def status(self, handle: AgentHandle) -> AgentStatus:
        current = self._require_handle(handle.agent_id)
        return current.status

    def schedule_for(self, handle: AgentHandle) -> str | None:
        self._require_handle(handle.agent_id)
        return self._schedules.get(handle.agent_id)

    def results(self, handle: AgentHandle) -> tuple[RunResult, ...]:
        self._require_handle(handle.agent_id)
        return tuple(self._runs.get(handle.agent_id, ()))

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

    def _result(self, handle: AgentHandle, task: AgentTask, *, status: str) -> RunResult:
        return RunResult(
            run_id=str(uuid4()),
            agent_id=handle.agent_id,
            org_id=handle.org_id,
            domain_id=handle.domain_id,
            task_class=task.task_class,
            status=status,
            opportunity_ids=_string_list(task.payload.get("opportunity_ids")),
            draft_ids=_string_list(task.payload.get("draft_ids")),
            usage_record_ids=_string_list(task.payload.get("usage_record_ids")),
            created_at=datetime.now(UTC),
        )

    def _append_action_history(
        self, agent_id: str, task: AgentTask, result: RunResult
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
            }
        )
        memory["action_history"] = history
        self._memory[agent_id] = memory


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list | tuple):
        return [item for item in value if isinstance(item, str)]
    return []
