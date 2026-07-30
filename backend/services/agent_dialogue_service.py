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
    BriefOutputInvalid,
    project_agent_session_detail,
)
from backend.services.agent_dialogue_repository import AgentDialogueRepository
from backend.services.agent_brief_agent import BriefAgent


class AgentDialogueService:
    """Owns authorization-aware state changes; does not call any model/tool."""

    def __init__(self, repository: AgentDialogueRepository, brief_agent: BriefAgent | None = None):
        self.repository, self.brief_agent = repository, brief_agent or BriefAgent()

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
        session, replayed = self.repository.append_user_message(
            session_id, user_id, text.strip(), client_turn_id, expected_status, expected_version,
        )
        if replayed:
            return self._detail(session_id, user_id), True
        status = AgentSessionStatus(session["status"])
        if status not in {AgentSessionStatus.EXTRACTING_BRIEF, AgentSessionStatus.WAITING_BRIEF_CONFIRMATION}:
            raise AgentSessionStateConflict()
        step = self.repository.append_step(session_id, user_id, "extracting_brief", "running", tool_name="brief_agent")
        rebuild_all = any(marker in text for marker in ("全部重新理解", "全部重来", "换一个方向", "推翻刚才方案"))
        try:
            if status is AgentSessionStatus.WAITING_BRIEF_CONFIRMATION:
                current = self.repository.get_session(session_id, user_id).get("brief_json")
                import json
                current = json.loads(current) if isinstance(current, str) else (current or {})
                proposal = self.brief_agent.revise_brief(current, text.strip(), rebuild_all)
            else:
                proposal = self.brief_agent.propose_brief(text.strip())
            self.repository.finish_brief(session_id, user_id, brief=proposal.model_dump(), summary=proposal.user_facing_summary, step_id=step["id"])
        except Exception as error:
            code = getattr(error, "code", "BRIEF_OUTPUT_INVALID")
            message = getattr(error, "message", "Brief proposal could not be completed.")
            stable = {"code": code, "message": message, "retryable": getattr(error, "retryable", False), "stage": "extracting_brief"}
            self.repository.fail_step(session_id, user_id, step["id"], stable)
            self.repository.mark_failed(session_id, user_id, error_code=code, error=stable)
            raise error if hasattr(error, "code") else BriefOutputInvalid() from error
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
    ) -> AgentSessionDetailResponse:
        """Store an idempotent receipt but intentionally execute no decision."""
        if decision != "confirm_brief":
            self.repository.record_unsupported_decision(session_id, user_id, decision_id, decision, expected_status, expected_version)
            raise AgentDecisionNotSupported()
        self.repository.confirm_brief(session_id, user_id, decision_id, expected_version)
        return self._detail(session_id, user_id)
