"""Thin composition service; it reads owner-scoped state but never mutates it."""

from __future__ import annotations

import uuid
from typing import Any

from backend.agents.runtime import RuntimeContext, RuntimeInput

from .definition import DESIGN_CONVERSATION_DEFINITION


class DesignConversationService:
    def __init__(self, runtime_engine, state_reader, cultural_rag=None) -> None:
        self.runtime_engine = runtime_engine
        self.state_reader = state_reader
        self.cultural_rag = cultural_rag

    async def run_turn(self, user_id: str, session_id: str, user_input: str, context_payload: dict[str, Any] | None = None):
        state = self.state_reader(user_id, session_id)
        status = str(state.get("status", "created"))
        context = RuntimeContext(
            user_id=user_id, session_id=session_id, agent_name=DESIGN_CONVERSATION_DEFINITION.name,
            session_status=status,
            services={"design_state_reader": self.state_reader, "cultural_rag": self.cultural_rag,
                      "design_runtime_state": {"retrieved_source_ids": set(), "loaded_skill_ids": set()}},
        )
        return await self.runtime_engine.run(
            DESIGN_CONVERSATION_DEFINITION, context,
            RuntimeInput(text=user_input, request_id=str(uuid.uuid4()), context_payload=context_payload or {}),
        )
