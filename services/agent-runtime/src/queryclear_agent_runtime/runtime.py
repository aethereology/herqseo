from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from uuid import uuid4


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
    payload: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class RunResult:
    run_id: str
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
        self._memory: dict[str, dict[str, object]] = {}
        self._schedules: dict[str, str] = {}

    def provision(self, org_id: str, domain_id: str) -> AgentHandle:
        handle = AgentHandle(
            agent_id=str(uuid4()),
            org_id=org_id,
            domain_id=domain_id,
            status=AgentStatus.ACTIVE,
            memory_store_ref=f"memory://{org_id}/{domain_id}",
        )
        self._handles[handle.agent_id] = handle
        self._memory[handle.agent_id] = {
            "brand_profile": {},
            "site_map": {},
            "action_history": [],
        }
        return handle

    def run(self, handle: AgentHandle, task: AgentTask) -> RunResult:
        if self.status(handle) == AgentStatus.PAUSED:
            return RunResult(
                run_id=str(uuid4()),
                status="failed",
                opportunity_ids=[],
                draft_ids=[],
                usage_record_ids=[],
                created_at=datetime.now(UTC),
            )

        result_status = "needs_approval" if task.autonomy_mode == "review" else "completed"
        return RunResult(
            run_id=str(uuid4()),
            status=result_status,
            opportunity_ids=[],
            draft_ids=[],
            usage_record_ids=[],
            created_at=datetime.now(UTC),
        )

    def get_memory(self, handle: AgentHandle) -> dict[str, object]:
        return dict(self._memory.get(handle.agent_id, {}))

    def set_memory(self, handle: AgentHandle, memory: dict[str, object]) -> None:
        self._memory[handle.agent_id] = dict(memory)

    def schedule(self, handle: AgentHandle, cadence: str) -> None:
        self._schedules[handle.agent_id] = cadence

    def pause(self, handle: AgentHandle) -> AgentHandle:
        return self._replace_status(handle, AgentStatus.PAUSED)

    def resume(self, handle: AgentHandle) -> AgentHandle:
        return self._replace_status(handle, AgentStatus.ACTIVE)

    def status(self, handle: AgentHandle) -> AgentStatus:
        current = self._handles.get(handle.agent_id, handle)
        return current.status

    def _replace_status(self, handle: AgentHandle, status: AgentStatus) -> AgentHandle:
        updated = AgentHandle(
            agent_id=handle.agent_id,
            org_id=handle.org_id,
            domain_id=handle.domain_id,
            status=status,
            memory_store_ref=handle.memory_store_ref,
        )
        self._handles[handle.agent_id] = updated
        return updated
