"""Application service for the round-one Agent dialogue state machine."""

from __future__ import annotations

from typing import Any

from backend.domain.agent_dialogue import (
    ALLOWED_TRANSITIONS,
    AgentDecisionNotSupported,
    AgentInvalidTransition,
    AgentSessionDetailResponse,
    AgentSessionStateConflict,
    AgentSessionStatus,
    project_agent_session_detail,
)
from backend.services.agent_dialogue_repository import AgentDialogueRepository


class AgentDialogueService:
    """Owns authorization-aware state changes; does not call any model/tool."""

    def __init__(self, repository: AgentDialogueRepository):
        self.repository = repository

    def _detail(self, session_id: str, user_id: str) -> AgentSessionDetailResponse:
        session, messages, steps = self.repository.get_detail_rows(session_id, user_id)
        return project_agent_session_detail(session, messages, steps)

    def create_session(self, user_id: str) -> AgentSessionDetailResponse:
        session = self.repository.create_session(user_id)
        return project_agent_session_detail(session, [], [])

    def get_session(self, session_id: str, user_id: str) -> AgentSessionDetailResponse:
        return self._detail(session_id, user_id)

    def append_message(
        self, session_id: str, user_id: str, *, text: str, client_turn_id: str,
        expected_status: AgentSessionStatus | None = None, expected_version: int | None = None,
    ) -> tuple[AgentSessionDetailResponse, bool]:
        _session, replayed = self.repository.append_user_message(
            session_id, user_id, text.strip(), client_turn_id, expected_status, expected_version,
        )
        # The response is a newly projected snapshot, never the repository row.
        return self._detail(session_id, user_id), replayed

    def append_step(self, session_id: str, user_id: str, **kwargs: Any) -> AgentSessionDetailResponse:
        self.repository.append_step(session_id, user_id, **kwargs)
        return self._detail(session_id, user_id)

    def transition(
        self, session_id: str, user_id: str, target: AgentSessionStatus,
        *, expected_status: AgentSessionStatus | None = None, expected_version: int | None = None,
    ) -> AgentSessionDetailResponse:
        current = self.repository.get_session(session_id, user_id)
        current_status = AgentSessionStatus(current["status"])
        if target not in ALLOWED_TRANSITIONS[current_status]:
            raise AgentInvalidTransition()
        self.repository.transition(
            session_id, user_id, target, expected_status or current_status, expected_version,
        )
        return self._detail(session_id, user_id)

    def mark_failed(
        self, session_id: str, user_id: str, *, error_code: str, message: str,
        retryable: bool = False, expected_version: int | None = None,
    ) -> AgentSessionDetailResponse:
        current = self.repository.get_session(session_id, user_id)
        if current.get("status") in {AgentSessionStatus.COMPLETED.value, AgentSessionStatus.FAILED.value}:
            raise AgentSessionStateConflict()
        self.repository.mark_failed(
            session_id, user_id, error_code=error_code,
            error={"code": error_code, "message": message, "retryable": retryable, "stage": current.get("current_stage")},
            expected_version=expected_version,
        )
        return self._detail(session_id, user_id)

    def submit_decision(
        self, session_id: str, user_id: str, *, decision_id: str, decision: str,
        expected_status: AgentSessionStatus, expected_version: int | None = None,
    ) -> None:
        """Store an idempotent receipt but intentionally execute no decision."""
        self.repository.record_unsupported_decision(
            session_id, user_id, decision_id, decision, expected_status, expected_version,
        )
        raise AgentDecisionNotSupported()
