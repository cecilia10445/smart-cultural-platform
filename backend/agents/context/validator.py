"""Closed-world validation for derived conversation context.

The summary is useful model input, but it is never a new source of truth.  This
module deliberately rejects questionable model output instead of trying to
repair it silently.
"""
from __future__ import annotations

from .models import ContextBudget, ContextFact, ContextSummaryV2, ContextValidationScope, FactSource
def estimate_tokens(value) -> int:
    return max(1, (len(str(value).encode("utf-8")) + 2) // 3)


class ContextSummaryValidationError(ValueError):
    pass


class ContextSummaryValidator:
    def __init__(self, budget: ContextBudget | None = None) -> None:
        self.budget = budget or ContextBudget()

    def validate(self, candidate: ContextSummaryV2, previous: ContextSummaryV2 | None,
                 scope: ContextValidationScope) -> ContextSummaryV2:
        errors: list[str] = []
        if candidate.session_id != scope.session_id:
            errors.append("session_id_mismatch")
        if candidate.source_message_count < (previous.source_message_count if previous else 0):
            errors.append("source_range_regressed")
        if candidate.source_message_count > scope.source_end_index:
            errors.append("source_range_out_of_bounds")
        if candidate.source_message_count and (not candidate.source_message_end_id or
                                               candidate.source_message_end_id not in scope.message_ids):
            errors.append("invalid_source_range")
        if candidate.source_message_end_id and scope.message_order:
            expected_count = scope.message_order.index(candidate.source_message_end_id) + 1
            if candidate.source_message_count != expected_count:
                errors.append("source_range_count_mismatch")
        for fact in self._facts(candidate):
            if not set(fact.source_message_ids).issubset(scope.message_ids):
                errors.append("unknown_message_id")
            if fact.source_type is FactSource.USER_CONFIRMED:
                cited = [scope.message_text_by_id.get(message_id, "") for message_id in fact.source_message_ids]
                if not cited or not any(fact.value in text for text in cited):
                    errors.append("unsupported_user_fact")
            if fact.source_type is FactSource.MODEL_INFERRED and fact in candidate.confirmed_constraints:
                errors.append("inferred_constraint")
            if fact.source_type is FactSource.TOOL_OBSERVED and fact in candidate.confirmed_constraints:
                errors.append("tool_observation_promoted")
        for ref in candidate.cultural_evidence_refs:
            if str(ref.get("source_id", "")) not in scope.source_ids:
                errors.append("unknown_source_id")
        for ref in candidate.loaded_skill_refs:
            if str(ref.get("skill_id", "")) not in scope.skill_ids:
                errors.append("unknown_skill_id")
        if scope.current_artifact_version is not None:
            for artifact in candidate.current_artifacts:
                if artifact.get("version") not in (None, scope.current_artifact_version):
                    errors.append("stale_artifact_version")
        if previous:
            old_rejected = {fact.value for fact in previous.rejected_directions}
            new_rejected = {fact.value for fact in candidate.rejected_directions}
            if not old_rejected.issubset(new_rejected):
                errors.append("rejected_direction_lost")
            # A question can disappear only when the newly compressed source says it is answered.
            old_questions = {fact.value for fact in previous.unresolved_questions}
            new_questions = {fact.value for fact in candidate.unresolved_questions}
            removed = old_questions - new_questions
            if removed and not any("answered" in item.lower() for item in candidate.pending_actions):
                errors.append("unresolved_question_lost")
        if estimate_tokens(candidate.model_dump(mode="json")) > self.budget.max_summary_tokens:
            errors.append("summary_budget_exceeded")
        if errors:
            raise ContextSummaryValidationError(",".join(sorted(set(errors))))
        return candidate

    @staticmethod
    def _facts(summary: ContextSummaryV2):
        groups = (summary.confirmed_constraints, summary.tentative_preferences,
                  summary.design_decisions, summary.rejected_directions,
                  summary.unresolved_questions)
        if summary.user_goal:
            yield summary.user_goal
        for group in groups:
            yield from group
