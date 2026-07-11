from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any


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


# The first real implementation is ClaudeAgentRuntime (claude_runtime.py),
# built on the Claude Agent SDK (D14). Program to the interface above, never
# to the framework (D7).
