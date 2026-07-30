"""Pydantic AI 2.14 FunctionModel adapter backed by the project runtime kernel."""

from __future__ import annotations

from dataclasses import dataclass, replace
import json
import uuid
from typing import Any

from pydantic_ai import Agent, RunContext, UsageLimits
from pydantic_ai.exceptions import UnexpectedModelBehavior, UsageLimitExceeded
from pydantic_ai.toolsets import FunctionToolset
from openai import APITimeoutError, APIConnectionError

from ..context import RuntimeContext
from ..executor import ToolCallLedger, ToolExecutor
from ..models import AgentDefinition, AgentRunResult, AgentRunStatus, RuntimeInput, RuntimeUsage, ToolCall, ToolError
from ..trace import TraceRecorder, fields_summary


class _ApprovalPause(BaseException):
    def __init__(self, approval: Any) -> None:
        self.approval = approval


@dataclass(slots=True)
class _AdapterDeps:
    definition: AgentDefinition
    context: RuntimeContext
    executor: ToolExecutor
    usage: RuntimeUsage
    ledger: ToolCallLedger
    trace: TraceRecorder
    results: list


class PydanticAIRuntimeEngine:
    """Runs Pydantic AI's native tool loop while delegating each call to A0.

    ``FunctionToolset.prepare`` replaces Pydantic's inferred wrapper schema with
    the ToolSpec Pydantic schema before it is shown to the model. The wrapper
    itself accepts ``**arguments`` and sends the unmodified call ID and values
    through ToolExecutor for project-owned validation and policy enforcement.
    """

    def __init__(self, executor: ToolExecutor, model: Any) -> None:
        self.executor = executor
        self.model = model

    async def run(self, definition: AgentDefinition, context: RuntimeContext, user_input: RuntimeInput) -> AgentRunResult:
        run_id = str(uuid.uuid4())
        usage = RuntimeUsage()
        trace = TraceRecorder(run_id)
        results: list = []
        deps = _AdapterDeps(definition, context, self.executor, usage, ToolCallLedger(), trace, results)
        trace.add("run_started", usage, input_summary={"request_id_present": bool(user_input.request_id), "text_length": len(user_input.text), "context_present": bool(user_input.context_payload)})
        toolset = self._toolset(definition, context)
        agent = Agent(
            self.model,
            output_type=definition.output_model,
            instructions=definition.instructions,
            deps_type=_AdapterDeps,
            toolsets=[toolset],
            name=definition.name,
            retries=0,
            defer_model_check=True,
            model_settings={"parallel_tool_calls": False},
        )
        try:
            result = await agent.run(
                self._model_prompt(user_input),
                deps=deps,
                usage_limits=UsageLimits(request_limit=definition.max_model_requests),
            )
        except _ApprovalPause as signal:
            return AgentRunResult(run_id=run_id, status=AgentRunStatus.PENDING_APPROVAL,
                                  pending_approval=signal.approval, tool_results=results,
                                  traces=trace.records, usage=usage)
        except UsageLimitExceeded:
            return self._failed(run_id, usage, trace, results, "MODEL_REQUEST_LIMIT_EXCEEDED", "budget_exceeded")
        except UnexpectedModelBehavior:
            return self._failed(run_id, usage, trace, results, "RUNTIME_MODEL_RESPONSE_INVALID", "run_failed")
        except APITimeoutError:
            return self._failed(run_id, usage, trace, results, "RUNTIME_MODEL_TIMEOUT", "run_failed")
        except APIConnectionError:
            return self._failed(run_id, usage, trace, results, "RUNTIME_PROVIDER_UNAVAILABLE", "run_failed")
        except Exception:
            return self._failed(run_id, usage, trace, results, "RUNTIME_EXECUTION_FAILED", "run_failed")
        usage.model_requests = result.usage.requests
        try:
            output = definition.output_model.model_validate(result.output).model_dump(mode="json")
        except Exception:
            return self._failed(run_id, usage, trace, results, "FINAL_OUTPUT_INVALID", "run_failed")
        trace.add("final_output", usage, success=True, output_summary=fields_summary(output))
        return AgentRunResult(run_id=run_id, status=AgentRunStatus.COMPLETED, final_output=output,
                              tool_results=results, traces=trace.records, usage=usage)

    def _toolset(self, definition: AgentDefinition, context: RuntimeContext) -> FunctionToolset:
        toolset = FunctionToolset(sequential=True)
        for spec in self.executor.registry.list_for_agent(definition.name, context.session_status):
            if spec.name not in definition.allowed_tools:
                continue
            invoke = self._make_invoke(spec)
            prepare = self._make_prepare(spec)
            toolset.add_function(invoke, takes_ctx=True, name=spec.name, description=spec.description,
                                 retries=0, prepare=prepare, sequential=True)
        return toolset

    @staticmethod
    def _make_invoke(spec):
        async def invoke(ctx: RunContext[_AdapterDeps], **arguments: Any) -> dict[str, Any]:
            deps = ctx.deps
            deps.usage.model_requests = ctx.usage.requests
            call = ToolCall(tool_call_id=ctx.tool_call_id or str(uuid.uuid4()), tool_name=spec.name, arguments=arguments)
            outcome = await deps.executor.execute(deps.definition, deps.context, call, deps.usage, deps.ledger, deps.trace)
            deps.results.append(outcome.result)
            if outcome.pending_approval is not None:
                # Pydantic AI's native deferred tool path skips the handler;
                # project Policy must first create the PendingApproval.
                raise _ApprovalPause(outcome.pending_approval)
            return outcome.result.model_dump(mode="json")
        return invoke

    @staticmethod
    def _make_prepare(spec):
        async def prepare(_ctx: RunContext[_AdapterDeps], tool_def):
            return replace(tool_def, name=spec.name, description=spec.description,
                           parameters_json_schema=spec.input_model.model_json_schema(), sequential=True)
        return prepare

    @staticmethod
    def _model_prompt(user_input: RuntimeInput) -> str:
        if not user_input.context_payload:
            return user_input.text
        # The current user text is also in the envelope, making the precedence
        # relation explicit for function models and production providers alike.
        return ("[PROJECT_CONVERSATION_CONTEXT]\n" + json.dumps(user_input.context_payload, ensure_ascii=False, sort_keys=True) +
                "\n[/PROJECT_CONVERSATION_CONTEXT]\n[CURRENT_USER_INPUT]\n" + user_input.text + "\n[/CURRENT_USER_INPUT]")

    @staticmethod
    def _failed(run_id: str, usage: RuntimeUsage, trace: TraceRecorder, results: list, code: str, event: str) -> AgentRunResult:
        trace.add(event, usage, success=False, error_code=code)
        return AgentRunResult(run_id=run_id, status=AgentRunStatus.FAILED,
                              error=ToolError(code=code, message=code), tool_results=results,
                              traces=trace.records, usage=usage)
