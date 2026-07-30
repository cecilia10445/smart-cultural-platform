"""Control-plane orchestration: short DB transactions around a read-only runtime."""
from __future__ import annotations
import asyncio

from backend.agents.design_conversation import DesignConversationService


class AgentRuntimeTurnService:
    def __init__(self, repository, design_service: DesignConversationService):
        self.repository, self.design_service = repository, design_service

    async def run_turn(self, user_id, session_id, content, client_turn_id):
        run, replayed = self.repository.create_or_get_run(session_id, user_id, client_turn_id, "design_conversation")
        if replayed:
            return run, True
        result = await self.design_service.run_turn(user_id, session_id, content)
        final = result.final_output or {}
        visible = final.get("result", final)
        kind = visible.get("kind", "runtime_result") if isinstance(visible, dict) else "runtime_result"
        text = visible.get("answer") or visible.get("question") or visible.get("summary") or visible.get("reason_summary") or kind
        persisted = self.repository.complete_run(run, result, content, str(text), {"runtime_run_id": run["id"], "output": final})
        return persisted, False
