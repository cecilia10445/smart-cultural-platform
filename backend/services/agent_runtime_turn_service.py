"""Control-plane orchestration: short DB transactions around a read-only runtime."""
from __future__ import annotations
import asyncio

from backend.agents.design_conversation import DesignConversationService
from backend.agents.context import RuntimeContextBuilder


class AgentRuntimeTurnService:
    def __init__(self, repository, design_service: DesignConversationService, context_builder=None):
        self.repository, self.design_service = repository, design_service
        self.context_builder = context_builder or (RuntimeContextBuilder(repository) if hasattr(repository, "get_active_summary") else None)

    async def run_turn(self, user_id, session_id, content, client_turn_id):
        run, replayed = self.repository.create_or_get_run(session_id, user_id, client_turn_id, "design_conversation")
        if replayed:
            return run, True
        context_payload = {}
        if self.context_builder is not None:
            context_payload = await self.context_builder.build(user_id, session_id, content)
        result = await (self.design_service.run_turn(user_id, session_id, content, context_payload)
                        if context_payload else self.design_service.run_turn(user_id, session_id, content))
        result.context_metadata = {key: value for key, value in context_payload.items()
                                   if key in {"summary_id", "summary_version", "compression_triggered", "compression_reason",
                                              "estimated_tokens_before", "estimated_tokens_after", "messages_summarized",
                                              "recent_messages_included", "summarizer_type", "fallback_used", "validation_warnings"}}
        final = result.final_output or {}
        visible = final.get("result", final)
        kind = visible.get("kind", "runtime_result") if isinstance(visible, dict) else "runtime_result"
        text = visible.get("answer") or visible.get("question") or visible.get("summary") or visible.get("reason_summary") or kind
        persisted = self.repository.complete_run(run, result, content, str(text), {"runtime_run_id": run["id"], "output": final})
        return persisted, False
