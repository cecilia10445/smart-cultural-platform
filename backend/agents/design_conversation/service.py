"""Thin composition service; it reads owner-scoped state but never mutates it."""

from __future__ import annotations

import uuid
from dataclasses import replace
from typing import Any

from backend.agents.runtime import AgentRunStatus, RuntimeContext, RuntimeInput
from .conversation_policy import ConversationPolicy
from .definition import DESIGN_CONVERSATION_DEFINITION


class DesignConversationService:
    def __init__(self, runtime_engine, state_reader, cultural_rag=None) -> None:
        self.runtime_engine = runtime_engine
        self.state_reader = state_reader
        self.cultural_rag = cultural_rag
        self.conversation_policy = ConversationPolicy()

    async def run_turn(self, user_id: str, session_id: str, user_input: str, context_payload: dict[str, Any] | None = None):
        state = self.state_reader(user_id, session_id)
        status = str(state.get("status", "created"))
        context = RuntimeContext(
            user_id=user_id, session_id=session_id, agent_name=DESIGN_CONVERSATION_DEFINITION.name,
            session_status=status,
            services={"design_state_reader": self.state_reader, "cultural_rag": self.cultural_rag,
                      "design_runtime_state": {"retrieved_source_ids": set(), "loaded_skill_ids": set()},
                      "conversation_context": context_payload or {}},
        )
        # A conversation is intentionally not routed through a hidden product
        # state machine.  The model may answer, research, propose a formal
        # action, or use an eligible read-only tool on every turn.  Side
        # effects are still gated later by the Action Policy and approval.
        definition = self._definition_for_turn(user_input)
        result = await self.runtime_engine.run(
            definition, context,
            RuntimeInput(text=user_input, request_id=str(uuid.uuid4()), context_payload=context_payload or {}),
        )
        metadata = self.conversation_policy.rag_metadata(result)
        if result.status is AgentRunStatus.COMPLETED and isinstance(result.final_output, dict):
            final_output = {**result.final_output, "rag_status": metadata["rag_status"]}
            result = result.model_copy(update={"final_output": final_output})
        invalid_structured_output = (result.status is AgentRunStatus.FAILED and result.error
                                     and result.error.code in {
                                         "RUNTIME_MODEL_RESPONSE_INVALID", "FINAL_OUTPUT_INVALID",
                                         "RUNTIME_OUTPUT_REPAIR_INVALID",
                                     }
                                     and bool(result.tool_results))
        if ((result.status is AgentRunStatus.FAILED and result.error and result.error.code == "MODEL_REQUEST_LIMIT_EXCEEDED"
                and any(record.error_code == "TOOL_CALL_LIMIT_EXCEEDED" for record in result.traces))
                or invalid_structured_output):
            output = self.conversation_policy.system_fallback(result)
            return result.model_copy(update={"status": AgentRunStatus.COMPLETED, "final_output": output, "error": None,
                                             "context_metadata": {**result.context_metadata, **metadata,
                                                                  "final_output_origin": "bounded_invalid_response_fallback" if invalid_structured_output else "bounded_tool_budget_fallback"}})
        return result.model_copy(update={"context_metadata": {**result.context_metadata, **metadata}})

    @staticmethod
    def _definition_for_turn(user_input: str):
        """Return one capability contract for the whole conversation.

        Keyword routing made a user's wording decide whether the Runtime could
        validate a proposal.  That coupled free conversation to a legacy
        linear workflow and caused identical intent to behave differently.
        The Runtime now receives one stable tool contract; the Action Policy
        remains the sole authority for side effects.
        """
        # Constraint validation belongs to the Action Policy after the Runtime
        # has proposed a command.  Keeping that write-oriented tool out of the
        # free conversation contract avoids a hidden keyword/state gate while
        # leaving research and other read-only tools available every turn.
        allowed = DESIGN_CONVERSATION_DEFINITION.allowed_tools - {"validate_design_constraints"}
        return replace(
            DESIGN_CONVERSATION_DEFINITION,
            allowed_tools=allowed,
            max_calls_by_tool={name: limit for name, limit in DESIGN_CONVERSATION_DEFINITION.max_calls_by_tool.items()
                               if name in allowed},
        )
