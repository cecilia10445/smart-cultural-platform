"""Safe sequential execution of one registered tool call."""

from __future__ import annotations

import asyncio
import inspect
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from .context import RuntimeContext
from .models import (
    AgentDefinition, PendingApproval, RuntimeUsage, ToolCall,
    ToolError, ToolErrorCode, ToolResult,
)
from .policy import ToolPolicy
from .tool_registry import ToolRegistry
from .trace import TraceRecorder, arguments_hash, canonical_arguments, fields_summary


@dataclass(slots=True)
class ToolCallLedger:
    entries: dict[str, tuple[str, str, ToolResult, PendingApproval | None]] = field(default_factory=dict)

    def replay_or_conflict(self, call: ToolCall) -> tuple[ToolResult | None, PendingApproval | None, bool]:
        signature = (call.tool_name, canonical_arguments(call.arguments))
        existing = self.entries.get(call.tool_call_id)
        if existing is None:
            return None, None, False
        if existing[:2] == signature:
            result = existing[2].model_copy(update={"replayed": True})
            return result, existing[3], False
        return ToolResult(
            tool_call_id=call.tool_call_id, tool_name=call.tool_name, ok=False, replayed=False,
            error=ToolError(code=ToolErrorCode.TOOL_CALL_ID_CONFLICT.value, message="tool call id conflicts with an earlier call"),
            duration_ms=0,
        ), None, True

    def record(self, call: ToolCall, result: ToolResult, approval: PendingApproval | None = None) -> None:
        self.entries[call.tool_call_id] = (call.tool_name, canonical_arguments(call.arguments), result, approval)


@dataclass(frozen=True, slots=True)
class ToolExecutionOutcome:
    result: ToolResult
    pending_approval: PendingApproval | None = None


class ToolExecutor:
    """A unique requested call consumes request budget even when later denied/invalid.

    Replays consume no budget. ``requested_*`` counts unique model requests;
    ``executed_*`` counts handler dispatches only.
    """

    def __init__(self, registry: ToolRegistry, policy: ToolPolicy | None = None) -> None:
        self.registry = registry
        self.policy = policy or ToolPolicy()

    async def execute(
        self,
        definition: AgentDefinition,
        context: RuntimeContext,
        call: ToolCall,
        usage: RuntimeUsage,
        ledger: ToolCallLedger,
        trace: TraceRecorder,
    ) -> ToolExecutionOutcome:
        replay, approval, conflict = ledger.replay_or_conflict(call)
        if replay is not None:
            trace.add("tool_replayed" if not conflict else "tool_failed", usage, tool_call_id=call.tool_call_id,
                      tool_name=call.tool_name, success=replay.ok, error_code=replay.error.code if replay.error else None,
                      arguments_hash=arguments_hash(call.arguments))
            return ToolExecutionOutcome(replay, approval)

        if usage.requested_tool_calls >= definition.max_total_tool_calls or usage.requested_calls_by_tool.get(call.tool_name, 0) >= definition.max_calls_per_tool:
            result = self._error(call, ToolErrorCode.TOOL_CALL_LIMIT_EXCEEDED)
            ledger.record(call, result)
            trace.add("budget_exceeded", usage, tool_call_id=call.tool_call_id, tool_name=call.tool_name,
                      success=False, error_code=result.error.code, arguments_hash=arguments_hash(call.arguments))
            return ToolExecutionOutcome(result)
        usage.requested_tool_calls += 1
        usage.requested_calls_by_tool[call.tool_name] = usage.requested_calls_by_tool.get(call.tool_name, 0) + 1
        trace.add("tool_requested", usage, tool_call_id=call.tool_call_id, tool_name=call.tool_name,
                  arguments_hash=arguments_hash(call.arguments), input_summary=fields_summary(call.arguments))

        spec = self.registry.get(call.tool_name)
        if spec is None:
            return self._record_failure(call, ledger, trace, usage, self._error(call, ToolErrorCode.TOOL_NOT_FOUND))
        try:
            input_value = spec.input_model.model_validate(call.arguments)
        except Exception:
            return self._record_failure(call, ledger, trace, usage, self._error(call, ToolErrorCode.TOOL_INPUT_INVALID), spec.risk)

        decision = self.policy.authorize(definition, context, spec, call)
        if not decision.allowed:
            if decision.approval_required:
                approval = PendingApproval(
                    approval_id=str(uuid.uuid4()), tool_call_id=call.tool_call_id, tool_name=call.tool_name,
                    arguments_summary=", ".join(sorted(call.arguments)) or "no arguments", risk=spec.risk,
                    reason=decision.reason, agent_name=context.agent_name, session_id=context.session_id,
                )
                result = self._error(call, ToolErrorCode.TOOL_APPROVAL_REQUIRED)
                ledger.record(call, result, approval)
                trace.add("approval_required", usage, tool_call_id=call.tool_call_id, tool_name=call.tool_name,
                          risk=spec.risk, success=False, error_code=result.error.code, arguments_hash=arguments_hash(call.arguments))
                return ToolExecutionOutcome(result, approval)
            result = self._error(call, decision.error_code or ToolErrorCode.TOOL_POLICY_DENIED)
            ledger.record(call, result)
            trace.add("policy_denied", usage, tool_call_id=call.tool_call_id, tool_name=call.tool_name,
                      risk=spec.risk, success=False, error_code=result.error.code, arguments_hash=arguments_hash(call.arguments))
            return ToolExecutionOutcome(result)
        trace.add("policy_allowed", usage, tool_call_id=call.tool_call_id, tool_name=call.tool_name,
                  risk=spec.risk, success=True, arguments_hash=arguments_hash(call.arguments))
        if usage.executed_calls_by_tool.get(spec.name, 0) >= spec.max_calls_per_run:
            return self._record_failure(call, ledger, trace, usage, self._error(call, ToolErrorCode.TOOL_CALL_LIMIT_EXCEEDED), spec.risk)

        started = time.perf_counter()
        usage.executed_tool_calls += 1
        usage.executed_calls_by_tool[spec.name] = usage.executed_calls_by_tool.get(spec.name, 0) + 1
        try:
            value = await asyncio.wait_for(self._invoke(spec.handler, context, input_value), timeout=spec.timeout_seconds)
        except asyncio.TimeoutError:
            result = self._error(call, ToolErrorCode.TOOL_TIMEOUT, self._elapsed_ms(started))
            return self._record_failure(call, ledger, trace, usage, result, spec.risk)
        except Exception:
            result = self._error(call, ToolErrorCode.TOOL_EXECUTION_FAILED, self._elapsed_ms(started))
            return self._record_failure(call, ledger, trace, usage, result, spec.risk)
        try:
            output = spec.output_model.model_validate(value).model_dump(mode="json")
        except Exception:
            result = self._error(call, ToolErrorCode.TOOL_OUTPUT_INVALID, self._elapsed_ms(started))
            return self._record_failure(call, ledger, trace, usage, result, spec.risk)
        result = ToolResult(tool_call_id=call.tool_call_id, tool_name=call.tool_name, ok=True, output=output,
                            duration_ms=self._elapsed_ms(started))
        ledger.record(call, result)
        trace.add("tool_completed", usage, tool_call_id=call.tool_call_id, tool_name=call.tool_name, risk=spec.risk,
                  success=True, duration_ms=result.duration_ms, arguments_hash=arguments_hash(call.arguments), output_summary=fields_summary(output))
        return ToolExecutionOutcome(result)

    async def _invoke(self, handler: Any, context: RuntimeContext, input_value: Any) -> Any:
        if inspect.iscoroutinefunction(handler):
            return await handler(context, input_value)
        value = await asyncio.to_thread(handler, context, input_value)
        if inspect.isawaitable(value):
            return await value
        return value

    @staticmethod
    def _elapsed_ms(started: float) -> int:
        return max(0, round((time.perf_counter() - started) * 1000))

    @staticmethod
    def _error(call: ToolCall, code: ToolErrorCode, duration_ms: int = 0) -> ToolResult:
        return ToolResult(tool_call_id=call.tool_call_id, tool_name=call.tool_name, ok=False,
                          error=ToolError(code=code.value, message=code.value), duration_ms=duration_ms)

    def _record_failure(self, call: ToolCall, ledger: ToolCallLedger, trace: TraceRecorder, usage: RuntimeUsage,
                        result: ToolResult, risk: Any = None) -> ToolExecutionOutcome:
        ledger.record(call, result)
        trace.add("tool_failed", usage, tool_call_id=call.tool_call_id, tool_name=call.tool_name, risk=risk,
                  success=False, error_code=result.error.code if result.error else None, duration_ms=result.duration_ms,
                  arguments_hash=arguments_hash(call.arguments))
        return ToolExecutionOutcome(result)
