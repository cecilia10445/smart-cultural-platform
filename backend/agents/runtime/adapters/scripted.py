"""Deterministic offline model-loop adapter for runtime contract tests."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any, Sequence

from ..context import RuntimeContext
from ..executor import ToolCallLedger, ToolExecutor
from ..models import (
    AgentDefinition, AgentRunResult, AgentRunStatus, RuntimeInput, RuntimeUsage,
    ToolCall, ToolError,
)
from ..trace import TraceRecorder, fields_summary


@dataclass(frozen=True, slots=True)
class ScriptedToolCallResponse:
    call: ToolCall


@dataclass(frozen=True, slots=True)
class ScriptedFinalResponse:
    output: Any


@dataclass(frozen=True, slots=True)
class ScriptedEmptyResponse:
    pass


@dataclass(frozen=True, slots=True)
class ScriptedMultipleToolCallsResponse:
    calls: tuple[ToolCall, ...]


class ScriptedRuntimeEngine:
    """Consumes one scripted model response per model request, without I/O."""

    def __init__(self, executor: ToolExecutor, responses: Sequence[object]) -> None:
        self.executor = executor
        self.responses = tuple(responses)

    async def run(self, definition: AgentDefinition, context: RuntimeContext, user_input: RuntimeInput) -> AgentRunResult:
        run_id = str(uuid.uuid4())
        usage = RuntimeUsage()
        trace = TraceRecorder(run_id)
        ledger = ToolCallLedger()
        results = []
        trace.add("run_started", usage, input_summary={"request_id_present": bool(user_input.request_id), "text_length": len(user_input.text)})
        index = 0
        while True:
            if usage.model_requests >= definition.max_model_requests:
                return self._failed(run_id, usage, trace, results, "MODEL_REQUEST_LIMIT_EXCEEDED", "budget_exceeded")
            response = self.responses[index] if index < len(self.responses) else ScriptedEmptyResponse()
            index += 1
            usage.model_requests += 1
            if isinstance(response, ScriptedEmptyResponse):
                return self._failed(run_id, usage, trace, results, "EMPTY_MODEL_RESPONSE", "run_failed")
            if isinstance(response, ScriptedMultipleToolCallsResponse):
                return self._failed(run_id, usage, trace, results, "MULTIPLE_TOOL_CALLS_NOT_ALLOWED", "run_failed")
            if isinstance(response, ScriptedFinalResponse):
                try:
                    output = definition.output_model.model_validate(response.output).model_dump(mode="json")
                except Exception:
                    return self._failed(run_id, usage, trace, results, "FINAL_OUTPUT_INVALID", "run_failed")
                trace.add("final_output", usage, success=True, output_summary=fields_summary(output))
                return AgentRunResult(run_id=run_id, status=AgentRunStatus.COMPLETED, final_output=output,
                                      tool_results=results, traces=trace.records, usage=usage)
            if not isinstance(response, ScriptedToolCallResponse):
                return self._failed(run_id, usage, trace, results, "INVALID_SCRIPTED_RESPONSE", "run_failed")
            outcome = await self.executor.execute(definition, context, response.call, usage, ledger, trace)
            results.append(outcome.result)
            if outcome.pending_approval is not None:
                return AgentRunResult(run_id=run_id, status=AgentRunStatus.PENDING_APPROVAL,
                                      pending_approval=outcome.pending_approval, tool_results=results,
                                      traces=trace.records, usage=usage)

    @staticmethod
    def _failed(run_id: str, usage: RuntimeUsage, trace: TraceRecorder, results: list, code: str, event: str) -> AgentRunResult:
        trace.add(event, usage, success=False, error_code=code)
        return AgentRunResult(run_id=run_id, status=AgentRunStatus.FAILED,
                              error=ToolError(code=code, message=code), tool_results=results,
                              traces=trace.records, usage=usage)
