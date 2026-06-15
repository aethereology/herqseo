from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Callable, Protocol
from uuid import uuid4


class BudgetExceeded(RuntimeError):
    pass


@dataclass(frozen=True)
class TokenBudget:
    org_id: str
    monthly_tokens: int
    used_tokens: int = 0
    soft_cap_ratio: float = 0.8

    @property
    def remaining_tokens(self) -> int:
        return max(self.monthly_tokens - self.used_tokens, 0)


@dataclass(frozen=True)
class ModelRequest:
    org_id: str
    domain_id: str
    task_class: str
    provider: str
    model: str
    estimated_input_tokens: int
    max_output_tokens: int

    @property
    def reserved_tokens(self) -> int:
        return self.estimated_input_tokens + self.max_output_tokens


@dataclass(frozen=True)
class ModelResponse:
    content: str
    input_tokens: int
    output_tokens: int
    cost_usd: Decimal

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


@dataclass(frozen=True)
class UsageRecord:
    id: str
    org_id: str
    domain_id: str
    task_class: str
    provider: str
    model: str
    input_tokens: int
    output_tokens: int
    cost_usd: Decimal
    created_at: datetime


@dataclass(frozen=True)
class BudgetState:
    budget: TokenBudget
    usage: UsageRecord
    soft_cap_reached: bool


class BudgetRepository(Protocol):
    def get_budget(self, org_id: str) -> TokenBudget:
        raise NotImplementedError

    def add_usage(self, record: UsageRecord) -> TokenBudget:
        raise NotImplementedError


class InMemoryBudgetRepository:
    def __init__(self, budgets: dict[str, TokenBudget] | None = None) -> None:
        self._budgets = budgets or {}
        self.records: list[UsageRecord] = []

    def get_budget(self, org_id: str) -> TokenBudget:
        try:
            return self._budgets[org_id]
        except KeyError as exc:
            raise BudgetExceeded(f"No token budget configured for org {org_id}") from exc

    def add_usage(self, record: UsageRecord) -> TokenBudget:
        budget = self.get_budget(record.org_id)
        used_tokens = budget.used_tokens + record.input_tokens + record.output_tokens
        updated = TokenBudget(
            org_id=budget.org_id,
            monthly_tokens=budget.monthly_tokens,
            used_tokens=used_tokens,
            soft_cap_ratio=budget.soft_cap_ratio,
        )
        self._budgets[record.org_id] = updated
        self.records.append(record)
        return updated


class TokenMeter:
    def __init__(self, budgets: BudgetRepository) -> None:
        self._budgets = budgets

    def run_metered(
        self,
        request: ModelRequest,
        invoke_model: Callable[[], ModelResponse],
    ) -> BudgetState:
        budget = self._budgets.get_budget(request.org_id)
        if budget.remaining_tokens <= 0:
            raise BudgetExceeded(f"Token budget exhausted for org {request.org_id}")

        if request.reserved_tokens > budget.remaining_tokens:
            raise BudgetExceeded(
                "Model call reservation exceeds remaining token budget "
                f"for org {request.org_id}"
            )

        response = invoke_model()
        record = UsageRecord(
            id=str(uuid4()),
            org_id=request.org_id,
            domain_id=request.domain_id,
            task_class=request.task_class,
            provider=request.provider,
            model=request.model,
            input_tokens=response.input_tokens,
            output_tokens=response.output_tokens,
            cost_usd=response.cost_usd,
            created_at=datetime.now(UTC),
        )
        updated_budget = self._budgets.add_usage(record)
        return BudgetState(
            budget=updated_budget,
            usage=record,
            soft_cap_reached=updated_budget.used_tokens
            >= updated_budget.monthly_tokens * updated_budget.soft_cap_ratio,
        )
