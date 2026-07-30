"""Incremental, bounded context construction for an agent turn."""
from __future__ import annotations

import json
from typing import Any, Protocol

from .models import ContextBudget, ContextFact, ContextSummaryV2, ContextValidationScope, FactSource
from .validator import ContextSummaryValidator, ContextSummaryValidationError


def estimate_tokens(value: Any) -> int:
    """Stable, provider-independent estimate used for a safety budget."""
    return max(1, (len(str(value).encode("utf-8")) + 2) // 3)


class ContextSummarizer(Protocol):
    async def summarize(self, previous_summary: ContextSummaryV2 | None, messages: list[dict[str, Any]],
                        session_state: dict[str, Any], validation_scope: ContextValidationScope | None = None) -> ContextSummaryV2: ...


class DeterministicContextSummarizer:
    """Conservative fallback.  It only copies statements which are explicit in rows."""
    async def summarize(self, previous_summary, messages, session_state, validation_scope=None):
        summary = previous_summary.model_copy(deep=True) if previous_summary else ContextSummaryV2(session_id=str(session_state["id"]))
        if messages:
            summary.source_message_start_id = summary.source_message_start_id or str(messages[0]["id"])
            summary.source_message_end_id = str(messages[-1]["id"])
            summary.source_message_count += len(messages)
        seen = {item.value for item in summary.rejected_directions}
        constraints = {item.value for item in summary.confirmed_constraints}
        questions = {item.value for item in summary.unresolved_questions}
        for message in messages:
            if message.get("role") != "user":
                continue
            text = str(message.get("content_text", "")).strip()
            if not text:
                continue
            fact = ContextFact(value=text[:72], source_type=FactSource.USER_CONFIRMED,
                               source_message_ids=[str(message["id"])], confidence=1)
            if summary.user_goal is None:
                summary.user_goal = fact
            if "不要" in text or "拒绝" in text:
                if fact.value not in seen:
                    summary.rejected_directions.append(fact); seen.add(fact.value)
            elif any(token in text for token in ("必须", "限定", "只要", "不能")):
                if fact.value not in constraints:
                    summary.confirmed_constraints.append(fact); constraints.add(fact.value)
            if "？" in text or "?" in text:
                if fact.value not in questions:
                    summary.unresolved_questions.append(fact); questions.add(fact.value)
            # Explicit confirmation resolves a matching earlier question without inventing a result.
            if any(token in text for token in ("确认", "就这样", "可以")):
                summary.unresolved_questions = [q for q in summary.unresolved_questions if q.value not in text]
        summary.current_artifacts = _current_artifacts(session_state)
        goal = summary.user_goal.value if summary.user_goal else "Session design context"
        summary.conversation_summary = goal[:500]
        # Keep the fallback structurally small: it is better to retain bounded,
        # attributable facts than to make a turn fail because the derived cache
        # became too large.
        for attribute in ("confirmed_constraints", "tentative_preferences", "design_decisions",
                          "rejected_directions", "unresolved_questions"):
            setattr(summary, attribute, getattr(summary, attribute)[-4:])
        return summary


class PydanticAIContextSummarizer:
    """Structured offline/online adapter.  Tests pass FunctionModel; production chooses its model externally."""
    def __init__(self, model: Any) -> None:
        self.model = model

    async def summarize(self, previous_summary, messages, session_state, validation_scope=None):
        from pydantic_ai import Agent
        payload = {
            "previous_summary": previous_summary.model_dump(mode="json") if previous_summary else None,
            "messages_to_compress": [_safe_message(message) for message in messages],
            "session_state": _safe_session_state(session_state),
            "validation_scope": validation_scope.model_dump(mode="json") if validation_scope else {},
        }
        agent = Agent(self.model, output_type=ContextSummaryV2, retries=0, defer_model_check=True,
                      instructions=("Produce a ContextSummaryV2 from supplied records only. Do not call tools. "
                                    "Never upgrade suggestions, tool observations, or inferences into confirmed facts."))
        result = await agent.run(json.dumps(payload, ensure_ascii=False, sort_keys=True))
        return ContextSummaryV2.model_validate(result.output)


class RuntimeContextBuilder:
    def __init__(self, repository, budget=None, summarizer=None, validator=None):
        self.repository = repository
        self.budget = budget or ContextBudget()
        self.summarizer = summarizer or DeterministicContextSummarizer()
        self.validator = validator or ContextSummaryValidator(self.budget)
        self.fallback = DeterministicContextSummarizer()

    async def build(self, user_id, session_id, current_input):
        session, messages, steps = self.repository.get_detail_rows(session_id, user_id)
        active = self.repository.get_active_summary(user_id, session_id) if hasattr(self.repository, "get_active_summary") else None
        previous = _summary_from_record(active)
        before = estimate_tokens(messages) + estimate_tokens(current_input)
        recent = self._select_recent(messages, previous, current_input)
        recent_ids = {str(row["id"]) for row in recent}
        after_previous = self.repository.get_messages_after_summary(user_id, session_id, previous.source_message_end_id if previous else None) if hasattr(self.repository, "get_messages_after_summary") else messages
        to_summarize = [row for row in after_previous if str(row["id"]) not in recent_ids]
        triggered = before > self.budget.compression_trigger_tokens or len(messages) > self.budget.compression_trigger_messages
        metadata = {"summary_id": active.get("id") if isinstance(active, dict) else None,
                    "summary_version": active.get("session_version") if isinstance(active, dict) else None,
                    "compression_triggered": False, "compression_reason": None,
                    "estimated_tokens_before": before, "messages_summarized": 0,
                    "recent_messages_included": len(recent), "summarizer_type": type(self.summarizer).__name__,
                    "fallback_used": False, "validation_warnings": []}
        if triggered and to_summarize:
            reason = "token_budget" if before > self.budget.compression_trigger_tokens else "message_budget"
            scope = self._scope(session_id, messages, session, steps)
            try:
                candidate = await self.summarizer.summarize(previous, to_summarize, session, scope)
                summary = self.validator.validate(candidate, previous, scope)
            except Exception as error:
                summary = await self.fallback.summarize(previous, to_summarize, session, scope)
                # The fallback is generated from the same closed set, and is validated too.
                summary = self.validator.validate(summary, previous, scope)
                metadata.update(fallback_used=True, validation_warnings=[f"context_summary_fallback:{type(error).__name__}"])
            record = (self.repository.create_summary_version(user_id, session_id, summary)
                      if hasattr(self.repository, "create_summary_version") else {})
            previous = summary
            metadata.update(summary_id=record.get("id"), summary_version=record.get("session_version"),
                            compression_triggered=True, compression_reason=reason,
                            messages_summarized=len(to_summarize))
            # Re-select so a just-compressed prefix is not needlessly duplicated.
            recent = self._select_recent(messages, previous, current_input)
            metadata["recent_messages_included"] = len(recent)
        estimated_after = estimate_tokens(previous.model_dump(mode="json")) if previous else 0
        estimated_after += estimate_tokens([_safe_message(row) for row in recent]) + estimate_tokens(current_input)
        metadata["estimated_tokens_after"] = estimated_after
        return {"session_state": _safe_session_state(session),
                "context_summary": previous.model_dump(mode="json") if previous else None,
                "recent_messages": [_safe_message(row) for row in recent], "current_user_input": current_input,
                "unresolved_questions": [item.model_dump(mode="json") for item in (previous.unresolved_questions if previous else [])],
                "confirmed_constraints": [item.model_dump(mode="json") for item in (previous.confirmed_constraints if previous else [])],
                "tentative_preferences": [item.model_dump(mode="json") for item in (previous.tentative_preferences if previous else [])],
                "rejected_directions": [item.model_dump(mode="json") for item in (previous.rejected_directions if previous else [])],
                **metadata}

    def _select_recent(self, messages, summary, current_input):
        # Walk backward within the budget. Important user language is preferentially retained.
        selected, used = [], estimate_tokens(current_input)
        summarized_end = summary.source_message_end_id if summary else None
        priority_ids = set()
        if summary:
            for fact in (*summary.rejected_directions, *summary.unresolved_questions):
                priority_ids.update(fact.source_message_ids)
        for row in reversed(messages):
            cost = estimate_tokens(_safe_message(row))
            important = str(row["id"]) in priority_ids or row.get("role") in {"user", "assistant"}
            if len(selected) < self.budget.min_recent_messages or (important and used + cost <= self.budget.max_recent_message_tokens):
                selected.append(row); used += cost
            if len(selected) >= self.budget.max_recent_messages:
                break
        selected.reverse()
        return selected

    def _scope(self, session_id, messages, session, steps):
        source_ids, skill_ids = set(), set()
        for step in steps:
            if step.get("skill_id"): skill_ids.add(str(step["skill_id"]))
            raw = step.get("tool_result_summary_json") or step.get("output_summary_json")
            if raw:
                try:
                    data = json.loads(raw) if isinstance(raw, str) else raw
                    source_ids.update(str(item.get("source_id")) for item in data.get("sources", []) if item.get("source_id"))
                except (TypeError, ValueError, AttributeError):
                    pass
        return ContextValidationScope(session_id=str(session_id), message_ids={str(row["id"]) for row in messages},
                                      source_ids=source_ids, skill_ids=skill_ids,
                                      current_artifact_version=session.get("text_revision_count"), source_end_index=len(messages),
                                      message_order=[str(row["id"]) for row in messages],
                                      message_text_by_id={str(row["id"]): str(row.get("content_text", "")) for row in messages})


def _summary_from_record(record):
    if not record: return None
    raw = record.get("summary") if isinstance(record, dict) else record
    if raw is None and isinstance(record, dict): raw = record.get("summary_json")
    if isinstance(raw, str): raw = json.loads(raw)
    return ContextSummaryV2.model_validate(raw)

def _safe_message(message):
    return {"id": str(message.get("id", "")), "role": str(message.get("role", "")),
            "message_type": str(message.get("message_type", "")), "text": str(message.get("content_text", ""))[:1000]}

def _safe_session_state(session):
    keys = ("id", "status", "current_stage", "version", "text_revision_count", "brief_json", "confirmed_text_json")
    return {key: session[key] for key in keys if key in session and session[key] is not None}

def _current_artifacts(session):
    if session.get("confirmed_text_json") is None: return []
    return [{"kind": "confirmed_text", "version": session.get("text_revision_count", 0)}]
