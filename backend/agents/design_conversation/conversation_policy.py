"""Small, deterministic safety policy around a model-driven conversation.

It never chooses a normal tool sequence or writes business state.  It only
projects safe RAG metadata and produces a useful bounded completion after a
provider/structured-output failure.
"""

from __future__ import annotations

from typing import Any

from backend.agents.runtime import AgentRunResult

from .outputs import ConversationReply


class ConversationPolicy:
    """One interpretation of RAG states and bounded continuation behavior."""

    @staticmethod
    def rag_metadata(result: AgentRunResult) -> dict[str, Any]:
        last: dict[str, Any] | None = None
        for tool_result in result.tool_results:
            if tool_result.tool_name != "search_cultural_knowledge" or not tool_result.ok:
                continue
            if isinstance(tool_result.output, dict):
                last = tool_result.output
        if not last:
            return {"rag_status": None, "rag_summary": None}
        status = last.get("status")
        if status == "matched":
            return {"rag_status": "matched", "rag_summary": "找到可引用的文化资料"}
        if status == "creative_only":
            return {"rag_status": "creative_only", "rag_summary": "当前文库没有可靠匹配，可按纯创意方向继续"}
        if status == "needs_clarification":
            return {"rag_status": "needs_clarification", "rag_summary": "文化检索主题仍不明确"}
        return {"rag_status": None, "rag_summary": None}

    def system_fallback(self, result: AgentRunResult) -> dict[str, Any]:
        """End safely without pretending a model completed the design work.

        Provider parsing and budget failures are operational states, not user
        intent.  The reply deliberately contains no fabricated question,
        Brief, source, suggestion, or business action.
        """
        return ConversationReply(
            message="这次回复未能完整生成，请重新尝试；你刚才的内容已保留。",
            intent="general_answer", rag_status=self.rag_metadata(result)["rag_status"],
            output_origin="system_fallback",
        ).model_dump(mode="json")
