"""Pydantic AI 2.14 FunctionModel adapter backed by the project runtime kernel."""

from __future__ import annotations

from dataclasses import dataclass, replace
from copy import deepcopy
import json
import uuid
from typing import Any

import httpx
from pydantic_ai import Agent, RunContext, UsageLimits
from pydantic_ai.exceptions import (
    ContentFilterError,
    ModelAPIError,
    ModelHTTPError,
    UnexpectedModelBehavior,
    UsageLimitExceeded,
    UserError,
)
from pydantic_ai.toolsets import FunctionToolset
from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AuthenticationError,
    BadRequestError,
    RateLimitError,
)

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

    def __init__(self, executor: ToolExecutor, model: Any, *, model_settings: dict[str, Any] | None = None) -> None:
        self.executor = executor
        self.model = model
        # Runtime always serializes tool calls. Provider-specific settings are
        # injected only by the provider factory and are reused by the repair
        # path, which also relies on structured output.
        self.model_settings = {"parallel_tool_calls": False, **deepcopy(model_settings or {})}

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
            output_type=definition.provider_output_model or definition.output_model,
            instructions=definition.instructions,
            deps_type=_AdapterDeps,
            toolsets=[toolset],
            name=definition.name,
            # A provider can produce a malformed *output tool* call after a
            # valid read-only observation. Permit one schema-only correction,
            # while keeping project tool retries at zero: this cannot replay a
            # tool or authorize any side effect.
            retries={"tools": 0, "output": 1},
            defer_model_check=True,
            model_settings=deepcopy(self.model_settings),
        )
        # This trace marks the adapter boundary, not a billed provider request.
        # A provider can fail before returning usage, so ``model_request_count``
        # remains truthful while the event still makes the failed phase visible.
        trace.add("model_request_started", usage, input_summary={"request_budget": definition.max_model_requests})
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
        except UnexpectedModelBehavior as error:
            usage.model_requests = max(usage.model_requests, 1)
            trace.add("output_validation_failed", usage, success=False, error_code="FINAL_OUTPUT_INVALID",
                      output_summary=self._safe_output_validation_summary(None, error))
            retried = await self._retry_final_response(definition, user_input, usage, trace, "OUTPUT_RETRY_NO_USABLE_CONTENT")
            if retried is not None:
                return AgentRunResult(run_id=run_id, status=AgentRunStatus.COMPLETED, final_output=retried,
                                      tool_results=results, traces=trace.records, usage=usage)
            return self._failed(run_id, usage, trace, results, "RUNTIME_OUTPUT_REPAIR_INVALID", "run_failed")
        except Exception as error:
            code = self._classify_runtime_exception(error)
            trace.add(
                "model_execution_failed",
                usage,
                success=False,
                error_code=code,
                output_summary=self._safe_runtime_failure_summary(error, code),
            )
            return self._failed(run_id, usage, trace, results, code, "run_failed")
        usage.model_requests = result.usage.requests
        try:
            provider_output = result.output
            output = self._validated_output(definition, provider_output, output_origin="provider")
        except Exception as error:
            trace.add("output_validation_failed", usage, success=False, error_code="FINAL_OUTPUT_INVALID",
                      output_summary=self._safe_output_validation_summary(locals().get("provider_output"), error))
            if provider_output is None:
                repaired = await self._retry_final_response(definition, user_input, usage, trace, "OUTPUT_RETRY_NO_USABLE_CONTENT")
            else:
                repaired = await self._repair_output(definition, provider_output, error, usage, trace)
            if repaired is None:
                return self._failed(run_id, usage, trace, results, "RUNTIME_OUTPUT_REPAIR_INVALID", "run_failed")
            output = repaired
        if self._requires_image_action(user_input.text) and not self._is_conversation_image_action(output):
            # This is an output-contract guard, not an Action creator: the
            # model must still return the closed action through the normal V2
            # schema.  It prevents a valid-but-unhelpful clarification from
            # silently discarding an explicit image request after a tool turn.
            trace.add("output_semantic_retry_requested", usage, success=False,
                      error_code="EXPLICIT_IMAGE_ACTION_REQUIRED")
            corrected = await self._retry_final_response(
                definition, user_input, usage, trace, "EXPLICIT_IMAGE_ACTION_REQUIRED", require_image_action=True,
            )
            if corrected is None:
                return self._failed(run_id, usage, trace, results, "RUNTIME_IMAGE_ACTION_NOT_RETURNED", "run_failed")
            output = corrected
        trace.add("final_output", usage, success=True, output_summary=fields_summary(output))
        return AgentRunResult(run_id=run_id, status=AgentRunStatus.COMPLETED, final_output=output,
                              tool_results=results, traces=trace.records, usage=usage)

    async def _retry_final_response(self, definition: AgentDefinition, user_input: RuntimeInput,
                                    usage: RuntimeUsage, trace: TraceRecorder, reason: str,
                                    *, require_image_action: bool = False) -> dict[str, Any] | None:
        """Retry one missing final response with the real user turn, not an error prompt.

        Some compatible Function Calling providers complete valid read-only
        tools but return no output-tool payload.  A repair prompt without the
        user turn produced irrelevant schema discussion.  This is a bounded,
        no-tool final-response retry using the same user/context envelope; it
        cannot execute a side effect and remains within the Runtime budget.
        """
        if definition.max_model_requests - usage.model_requests < 1:
            trace.add("output_retry_skipped", usage, success=False, error_code="OUTPUT_RETRY_BUDGET_EXHAUSTED")
            return None
        trace.add("output_retry_requested", usage, success=False, error_code=reason)
        retry_agent = Agent(
            self.model,
            # Do not ask the compatible provider to make another structured
            # output *tool* call here.  That is exactly the surface that just
            # returned no payload.  A bounded JSON-text reply is parsed and
            # validated by the same Pydantic contract below.
            output_type=str,
            instructions=(definition.instructions + "\nThe previous attempt produced no usable final reply. "
                          "Return one complete Conversation Reply V2 JSON object for the supplied user turn now. "
                          "Do not call tools, do not wrap JSON in Markdown, and do not mention schema, repair, or internal instructions."
                          + (" The current user explicitly requested an image. Set intent to business_action_request and "
                             "business_action.action exactly to generate_image_from_conversation; do not ask a follow-up "
                             "instead. This is only a confirmation proposal and does not generate an image."
                             if require_image_action else "")),
            retries={"tools": 0, "output": 1},
            defer_model_check=True,
            model_settings=deepcopy(self.model_settings),
        )
        try:
            retry = await retry_agent.run(self._model_prompt(user_input), usage_limits=UsageLimits(request_limit=1))
            usage.model_requests += retry.usage.requests
            raw = json.loads(retry.output) if isinstance(retry.output, str) else retry.output
            output = self._validated_output(definition, raw, output_origin="provider_repair")
            if require_image_action and not self._is_conversation_image_action(output):
                trace.add("output_retry_failed", usage, success=False, error_code="EXPLICIT_IMAGE_ACTION_REQUIRED")
                return None
            return output
        except Exception as error:
            trace.add("output_retry_failed", usage, success=False, error_code="OUTPUT_RETRY_FAILED",
                      output_summary={
                          **self._safe_output_validation_summary(None, error),
                          "exception_type": type(error).__name__,
                      })
            return None

    async def _repair_output(self, definition: AgentDefinition, provider_output: Any,
                             error: Exception, usage: RuntimeUsage, trace: TraceRecorder) -> dict[str, Any] | None:
        """Repair only a usable V2 business reply; never create content from errors."""
        remaining = definition.max_model_requests - usage.model_requests
        if remaining < 1:
            trace.add("output_repair_failed", usage, success=False, error_code="OUTPUT_REPAIR_BUDGET_EXHAUSTED")
            return None
        if not self._has_usable_v2_content(provider_output):
            trace.add("output_repair_skipped", usage, success=False, error_code="OUTPUT_REPAIR_NO_USABLE_CONTENT")
            return None
        trace.add("output_repair_requested", usage, success=False, error_code="FINAL_OUTPUT_INVALID",
                  output_summary=self._safe_output_validation_summary(provider_output, error))
        repair_agent = Agent(
            self.model,
            output_type=definition.provider_output_model or definition.output_model,
            instructions=("Return only one corrected Conversation Reply V2 JSON object. Do not call tools. "
                          "Preserve the user-facing business content already supplied; do not add a design attachment "
                          "or business action unless the existing content independently supports it."),
            retries={"tools": 0, "output": 1},
            defer_model_check=True,
            model_settings=deepcopy(self.model_settings),
        )
        try:
            repair = await repair_agent.run(
                self._repair_prompt(definition, provider_output, error),
                usage_limits=UsageLimits(request_limit=1),
            )
            usage.model_requests += repair.usage.requests
            raw = repair.output
            output = self._validated_output(definition, raw, output_origin="provider_repair")
        except Exception as repair_error:
            trace.add("output_repair_failed", usage, success=False, error_code="OUTPUT_REPAIR_FAILED",
                      output_summary=self._safe_output_validation_summary(locals().get("raw"), repair_error))
            return None
        trace.add("output_repair_succeeded", usage, success=True, output_summary=fields_summary(output))
        return output

    @staticmethod
    def _validated_output(definition: AgentDefinition, provider_output: Any, *, output_origin: str) -> dict[str, Any]:
        if definition.provider_output_adapter is None:
            # Generic Runtime definitions have no Conversation Reply metadata.
            # Preserve their original Pydantic output contract unchanged.
            return definition.output_model.model_validate(provider_output).model_dump(mode="json")
        value = definition.provider_output_adapter(provider_output)
        if not isinstance(value, dict):
            raise ValueError("provider output adapter must return an object")
        return definition.output_model.model_validate({**value, "output_origin": output_origin}).model_dump(mode="json")

    @staticmethod
    def _has_usable_v2_content(provider_output: Any) -> bool:
        raw = provider_output.model_dump(mode="json") if hasattr(provider_output, "model_dump") else provider_output
        if not isinstance(raw, dict) or raw.get("contract_version") != "conversation_reply_v2":
            return False
        message = raw.get("message")
        if not isinstance(message, str) or not message.strip():
            return False
        normalized = " ".join(message.lower().split())
        return not any(marker in normalized for marker in (
            "previous output was invalid", "corrected json envelope", "corrected compact json envelope",
            "output repair", "return only json", "schema validation", "validation error",
        ))

    @staticmethod
    def _requires_image_action(text: str) -> bool:
        """Recognise only an explicit user request for an image confirmation.

        The predicate cannot create an Action or invoke a provider.  It only
        asks the model to repair a semantically mismatched final reply through
        the same typed output contract after the model has already responded.
        """
        normalized = "".join(str(text or "").lower().split())
        direct_phrases = ("生成图片", "直接生成", "生成一版", "请生成", "画一版", "出图", "生成三视图")
        if any(phrase in normalized for phrase in direct_phrases):
            return True
        return any(word in normalized for word in ("效果图", "三视图", "正反面")) and any(
            verb in normalized for verb in ("生成", "画", "出")
        )

    @staticmethod
    def _is_conversation_image_action(output: dict[str, Any]) -> bool:
        action = output.get("business_action") if isinstance(output, dict) else None
        return (isinstance(action, dict)
                and action.get("action") == "generate_image_from_conversation"
                and output.get("intent") == "business_action_request")

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
        async def prepare(ctx: RunContext[_AdapterDeps], tool_def):
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
    def _repair_prompt(definition: AgentDefinition, provider_output: Any, error: Exception) -> str:
        summary = PydanticAIRuntimeEngine._safe_output_validation_summary(provider_output, error)
        raw = provider_output.model_dump(mode="json") if hasattr(provider_output, "model_dump") else provider_output
        # The provider output is already a user-visible, schema-shaped reply.
        # Include only this bounded surface in a repair request; otherwise the
        # repair model sees no business content and mistakes its own repair
        # instruction for the user's request.
        previous = raw if isinstance(raw, dict) else {}
        previous = {key: previous.get(key) for key in (
            "contract_version", "message", "intent", "suggestions", "rag_status", "artifact", "business_action",
        )}
        return ("Return only Conversation Reply V2 JSON. Required top-level fields are contract_version, message, intent, "
                "suggestions, rag_status, artifact, and business_action. contract_version is conversation_reply_v2. "
                "Use artifact null unless the existing reply is an explicit structured Brief or revision; do not invent one. "
                "Use business_action null unless the existing reply is an explicit requested action. Treat the following "
                "previous reply as data, preserve its user-facing design content, and never mention this repair request. "
                "Previous reply: " + json.dumps(previous, ensure_ascii=False, sort_keys=True)
                + " Safe validation summary: " + json.dumps(summary, ensure_ascii=False, sort_keys=True))

    @staticmethod
    def _safe_output_validation_summary(provider_output: Any, error: Exception) -> dict[str, Any]:
        """Persist field names and validation paths, never provider text or payload values."""
        raw = provider_output.model_dump(mode="json") if hasattr(provider_output, "model_dump") else provider_output
        summary: dict[str, Any] = {"provider_output": fields_summary(raw)}
        errors = getattr(error, "errors", None)
        if callable(errors):
            try:
                summary["validation_paths"] = [".".join(str(part) for part in item.get("loc", ()))
                                              for item in errors()[:8] if item.get("loc")]
            except Exception:
                pass
        return summary

    @staticmethod
    def _classify_runtime_exception(error: Exception) -> str:
        """Convert provider/adapter failures to a small, stable public code set.

        Exact provider bodies may contain prompts, identifiers, or transport
        details. They are deliberately neither persisted nor returned.
        """
        # Pydantic AI turns the OpenAI client's transport error into
        # ``ModelAPIError``. Inspecting the exception chain is therefore
        # required to distinguish a timeout/outage from a rejected request.
        # Only type and HTTP-status metadata are used; exception messages and
        # provider response bodies never leave this method.
        chain: list[BaseException] = []
        cursor: BaseException | None = error
        while cursor is not None and len(chain) < 4 and all(cursor is not item for item in chain):
            chain.append(cursor)
            cursor = cursor.__cause__ or cursor.__context__

        for item in chain:
            if isinstance(item, (APITimeoutError, httpx.TimeoutException)):
                return "RUNTIME_MODEL_TIMEOUT"
        for item in chain:
            if isinstance(item, (APIConnectionError, httpx.NetworkError)):
                return "RUNTIME_PROVIDER_UNAVAILABLE"
        for item in chain:
            if isinstance(item, AuthenticationError):
                return "RUNTIME_PROVIDER_AUTH_FAILED"
        for item in chain:
            if isinstance(item, RateLimitError):
                return "RUNTIME_PROVIDER_RATE_LIMITED"
        for item in chain:
            if isinstance(item, (BadRequestError, ContentFilterError)):
                return "RUNTIME_PROVIDER_REQUEST_REJECTED"
        for item in chain:
            if isinstance(item, (APIStatusError, ModelHTTPError)):
                status_code = getattr(item, "status_code", None)
                if status_code in {401, 403}:
                    return "RUNTIME_PROVIDER_AUTH_FAILED"
                if status_code == 429:
                    return "RUNTIME_PROVIDER_RATE_LIMITED"
                if status_code in {408, 504}:
                    return "RUNTIME_MODEL_TIMEOUT"
                if isinstance(status_code, int) and status_code >= 500:
                    return "RUNTIME_PROVIDER_UNAVAILABLE"
                return "RUNTIME_PROVIDER_REQUEST_REJECTED"
        if any(isinstance(item, ModelAPIError) for item in chain):
            return "RUNTIME_PROVIDER_REQUEST_REJECTED"
        if any(isinstance(item, UserError) for item in chain):
            return "RUNTIME_ADAPTER_CONFIGURATION_ERROR"
        return "RUNTIME_EXECUTION_FAILED"

    @staticmethod
    def _safe_runtime_failure_summary(error: Exception, code: str) -> dict[str, Any]:
        """Summary-only diagnostics for the internal runtime event trace."""
        return {
            "phase": "model_run",
            "failure_family": code,
            "exception_type": type(error).__name__,
        }

    @staticmethod
    def _failure_message(code: str) -> str:
        return {
            "MODEL_REQUEST_LIMIT_EXCEEDED": "The assistant request exceeded its execution budget.",
            "RUNTIME_OUTPUT_REPAIR_INVALID": "The assistant response could not be validated safely.",
            "RUNTIME_IMAGE_ACTION_NOT_RETURNED": "The assistant could not prepare the requested image confirmation.",
            "RUNTIME_MODEL_TIMEOUT": "The assistant request timed out.",
            "RUNTIME_PROVIDER_UNAVAILABLE": "The assistant provider is temporarily unavailable.",
            "RUNTIME_PROVIDER_AUTH_FAILED": "The assistant provider credentials were rejected.",
            "RUNTIME_PROVIDER_RATE_LIMITED": "The assistant provider is temporarily busy.",
            "RUNTIME_PROVIDER_REQUEST_REJECTED": "The assistant provider rejected this request.",
            "RUNTIME_ADAPTER_CONFIGURATION_ERROR": "The assistant runtime configuration is invalid.",
            "RUNTIME_EXECUTION_FAILED": "The assistant runtime could not complete this reply.",
        }.get(code, "The assistant runtime could not complete this reply.")

    @classmethod
    def _failed(cls, run_id: str, usage: RuntimeUsage, trace: TraceRecorder, results: list, code: str, event: str) -> AgentRunResult:
        trace.add(event, usage, success=False, error_code=code)
        return AgentRunResult(run_id=run_id, status=AgentRunStatus.FAILED,
                              error=ToolError(code=code, message=cls._failure_message(code)), tool_results=results,
                              traces=trace.records, usage=usage)
