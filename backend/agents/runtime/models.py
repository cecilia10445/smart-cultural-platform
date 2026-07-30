"""Framework-independent contracts for the offline agent runtime."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import json
from typing import Any, Awaitable, Callable

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ToolRisk(str, Enum):
    READ_ONLY = "READ_ONLY"
    LOW_RISK = "LOW_RISK"
    HIGH_RISK = "HIGH_RISK"
    FORBIDDEN = "FORBIDDEN"


class ToolErrorCode(str, Enum):
    TOOL_NOT_FOUND = "TOOL_NOT_FOUND"
    TOOL_INPUT_INVALID = "TOOL_INPUT_INVALID"
    TOOL_OUTPUT_INVALID = "TOOL_OUTPUT_INVALID"
    TOOL_POLICY_DENIED = "TOOL_POLICY_DENIED"
    TOOL_APPROVAL_REQUIRED = "TOOL_APPROVAL_REQUIRED"
    TOOL_FORBIDDEN = "TOOL_FORBIDDEN"
    TOOL_TIMEOUT = "TOOL_TIMEOUT"
    TOOL_EXECUTION_FAILED = "TOOL_EXECUTION_FAILED"
    TOOL_CALL_ID_CONFLICT = "TOOL_CALL_ID_CONFLICT"
    TOOL_CALL_LIMIT_EXCEEDED = "TOOL_CALL_LIMIT_EXCEEDED"


class ToolError(BaseModel):
    """A deliberately small error observation safe to pass to a model."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    code: str
    message: str


class ToolCall(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    tool_call_id: str = Field(min_length=1, max_length=128)
    tool_name: str = Field(min_length=1, max_length=64)
    arguments: dict[str, Any] = Field(default_factory=dict)

    @field_validator("arguments")
    @classmethod
    def arguments_must_be_json(cls, value: dict[str, Any]) -> dict[str, Any]:
        try:
            json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        except (TypeError, ValueError) as error:
            raise ValueError("Tool arguments must be JSON-compatible") from error
        return value


class ToolResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    tool_call_id: str
    tool_name: str
    ok: bool
    replayed: bool = False
    output: dict[str, Any] | None = None
    error: ToolError | None = None
    duration_ms: int = Field(ge=0)


class PendingApproval(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    approval_id: str
    tool_call_id: str
    tool_name: str
    arguments_summary: str
    risk: ToolRisk
    reason: str
    agent_name: str
    session_id: str


class RuntimeInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    text: str = Field(min_length=1, max_length=12000)
    request_id: str = Field(min_length=1, max_length=128)


class RuntimeUsage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model_requests: int = Field(default=0, ge=0)
    requested_tool_calls: int = Field(default=0, ge=0)
    executed_tool_calls: int = Field(default=0, ge=0)
    requested_calls_by_tool: dict[str, int] = Field(default_factory=dict)
    executed_calls_by_tool: dict[str, int] = Field(default_factory=dict)

    def snapshot(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class TraceRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: str
    step: int = Field(ge=0)
    event_type: str
    tool_call_id: str | None = None
    tool_name: str | None = None
    risk: ToolRisk | None = None
    success: bool | None = None
    error_code: str | None = None
    duration_ms: int | None = Field(default=None, ge=0)
    arguments_hash: str | None = None
    input_summary: dict[str, Any] | None = None
    output_summary: dict[str, Any] | None = None
    budget_snapshot: dict[str, Any] = Field(default_factory=dict)


class AgentRunStatus(str, Enum):
    COMPLETED = "completed"
    PENDING_APPROVAL = "pending_approval"
    FAILED = "failed"


class AgentRunResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    status: AgentRunStatus
    final_output: dict[str, Any] | None = None
    pending_approval: PendingApproval | None = None
    error: ToolError | None = None
    tool_results: list[ToolResult] = Field(default_factory=list)
    traces: list[TraceRecord] = Field(default_factory=list)
    usage: RuntimeUsage


Handler = Callable[[Any, BaseModel], BaseModel | dict[str, Any] | Awaitable[BaseModel | dict[str, Any]]]


def _require_pydantic_model(value: type[BaseModel], field_name: str) -> None:
    if not isinstance(value, type) or not issubclass(value, BaseModel):
        raise TypeError(f"{field_name} must be a Pydantic BaseModel subclass")


@dataclass(frozen=True, slots=True)
class ToolSpec:
    name: str
    description: str
    input_model: type[BaseModel]
    output_model: type[BaseModel]
    handler: Handler
    risk: ToolRisk
    allowed_agents: frozenset[str] = field(default_factory=frozenset)
    allowed_statuses: frozenset[str] = field(default_factory=frozenset)
    timeout_seconds: float = 10.0
    max_calls_per_run: int = 1

    def __post_init__(self) -> None:
        import re

        object.__setattr__(self, "allowed_agents", frozenset(self.allowed_agents))
        object.__setattr__(self, "allowed_statuses", frozenset(self.allowed_statuses))
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,63}", self.name):
            raise ValueError("Tool name must be a stable function-call identifier")
        if not self.description.strip():
            raise ValueError("Tool description must not be empty")
        if not isinstance(self.risk, ToolRisk):
            raise TypeError("risk must be a ToolRisk")
        _require_pydantic_model(self.input_model, "input_model")
        _require_pydantic_model(self.output_model, "output_model")
        if not callable(self.handler):
            raise TypeError("handler must be callable")
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if self.max_calls_per_run < 1:
            raise ValueError("max_calls_per_run must be at least one")
        if any(not isinstance(name, str) or not name.strip() for name in self.allowed_agents):
            raise ValueError("allowed_agents may not contain blank names")
        if any(not isinstance(status, str) or not status.strip() for status in self.allowed_statuses):
            raise ValueError("allowed_statuses may not contain blank statuses")


@dataclass(frozen=True, slots=True)
class AgentDefinition:
    name: str
    instructions: str
    allowed_tools: frozenset[str]
    output_model: type[BaseModel]
    max_model_requests: int = 4
    max_total_tool_calls: int = 4
    max_calls_per_tool: int = 2
    allow_parallel_tool_calls: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "allowed_tools", frozenset(self.allowed_tools))
        if not self.name.strip() or not self.instructions.strip():
            raise ValueError("Agent name and instructions must not be empty")
        if any(not isinstance(name, str) or not name.strip() for name in self.allowed_tools):
            raise ValueError("allowed_tools may not contain blank names")
        _require_pydantic_model(self.output_model, "output_model")
        if self.max_model_requests < 1 or self.max_total_tool_calls < 0 or self.max_calls_per_tool < 1:
            raise ValueError("Runtime budgets must be positive (tool total may be zero)")
        if self.allow_parallel_tool_calls:
            raise ValueError("A0 only supports sequential tool calls")

    @property
    def budget(self) -> "RuntimeBudget":
        return RuntimeBudget(self.max_model_requests, self.max_total_tool_calls, self.max_calls_per_tool)


@dataclass(frozen=True, slots=True)
class RuntimeBudget:
    """Distinct caps for model turns, all requested tools, and each tool name."""

    max_model_requests: int
    max_total_tool_calls: int
    max_calls_per_tool: int

    def __post_init__(self) -> None:
        if self.max_model_requests < 1 or self.max_total_tool_calls < 0 or self.max_calls_per_tool < 1:
            raise ValueError("Invalid runtime budget")


@dataclass(frozen=True, slots=True)
class ToolAuthorizationDecision:
    allowed: bool
    approval_required: bool = False
    error_code: ToolErrorCode | None = None
    reason: str = ""
