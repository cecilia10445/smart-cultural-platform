"""Application service for the round-one Agent dialogue state machine."""

from __future__ import annotations

import json
from typing import Any

from backend.domain.agent_dialogue import (
    ALLOWED_TRANSITIONS,
    AgentDecisionNotSupported,
    AgentInvalidTransition,
    AgentSessionDetailResponse,
    AgentSessionStateConflict,
    AgentSessionStatus,
    BriefOutputInvalid,
    ProductTextOutputInvalid,
    TextRevisionLimitReached,
    project_agent_session_detail,
)
from backend.services.agent_dialogue_repository import AgentDialogueRepository
from backend.services.agent_brief_agent import BriefAgent
from backend.services.agent_product_text import ProductTextService


class AgentDialogueService:
    """Owns owner-scoped state changes and invokes bounded stage adapters."""

    def __init__(
        self, repository: AgentDialogueRepository, brief_agent: BriefAgent | None = None,
        product_text_service: ProductTextService | None = None,
    ):
        self.repository = repository
        self.brief_agent = brief_agent or BriefAgent()
        self.product_text_service = product_text_service or ProductTextService()

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
        # A replay remains a replay even after the revision ceiling is reached.
        before = self.repository.get_session(session_id, user_id)
        if (
            before.get("status") == AgentSessionStatus.WAITING_TEXT_FEEDBACK.value
            and int(before.get("text_revision_count") or 0) >= 4
        ):
            if self.repository.has_client_turn(session_id, user_id, client_turn_id):
                return self._detail(session_id, user_id), True
            raise TextRevisionLimitReached()
        session, replayed = self.repository.append_user_message(
            session_id, user_id, text.strip(), client_turn_id, expected_status, expected_version,
        )
        if replayed:
            return self._detail(session_id, user_id), True
        status = AgentSessionStatus(session["status"])
        if status is AgentSessionStatus.WAITING_TEXT_FEEDBACK:
            if int(session.get("text_revision_count") or 0) >= 4:
                raise TextRevisionLimitReached()
            self.repository.transition(
                session_id, user_id, AgentSessionStatus.GENERATING_PRODUCT_TEXT,
                AgentSessionStatus.WAITING_TEXT_FEEDBACK, None,
            )
            self._generate_product_text(session_id, user_id, feedback=text.strip(), is_revision=True)
            return self._detail(session_id, user_id), False
        if status not in {AgentSessionStatus.EXTRACTING_BRIEF, AgentSessionStatus.WAITING_BRIEF_CONFIRMATION}:
            raise AgentSessionStateConflict()
        step = self.repository.append_step(session_id, user_id, "extracting_brief", "running", tool_name="brief_agent")
        rebuild_all = any(marker in text for marker in ("全部重新理解", "全部重来", "换一个方向", "推翻刚才方案"))
        try:
            if status is AgentSessionStatus.WAITING_BRIEF_CONFIRMATION:
                current = self._json_object(self.repository.get_session(session_id, user_id).get("brief_json"))
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

    @staticmethod
    def _json_object(value: Any) -> dict[str, Any]:
        if isinstance(value, dict):
            return value
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except ValueError:
                return {}
        return value if isinstance(value, dict) else {}

    @staticmethod
    def _product_summary(draft: dict[str, Any]) -> str:
        points = "；".join(item for item in draft.get("selling_points", []) if isinstance(item, str))
        return "\n".join((
            f"产品名称：{draft.get('product_name', '')}",
            f"设计理念：{draft.get('design_concept', '')}",
            f"文化转译：{draft.get('cultural_translation', '')}",
            f"产品结构：{draft.get('structure', '')}",
            f"材质：{draft.get('materials', '')}",
            f"配色：{draft.get('color_plan', '')}",
            f"使用场景：{draft.get('usage_scene', '')}",
            f"核心卖点：{points}",
            f"资料状态：{draft.get('evidence_status', '')}",
            f"使用的文本 Skill：{draft.get('selected_text_skill', '')}",
        ))

    def _generate_product_text(self, session_id: str, user_id: str, *, feedback: str | None, is_revision: bool) -> None:
        """Execute one bounded text stage outside repository transactions."""
        session = self.repository.get_session(session_id, user_id)
        brief_record = self._json_object(session.get("brief_json"))
        brief = self._json_object(brief_record.get("normalized_brief"))
        if not brief:
            raise AgentSessionStateConflict()
        current_draft = self._json_object(session.get("confirmed_text_json")) if is_revision else None
        retrieve_step = self.repository.append_step(
            session_id, user_id, "generating_product_text", "running", tool_name="retrieve_cultural_evidence",
            input_summary={"summary": "Retrieving compact cultural evidence"},
        )
        evidence = self.product_text_service.retrieve_cultural_evidence(brief)
        self.repository.finish_step(
            session_id, user_id, retrieve_step["id"],
            {"summary": "Cultural evidence retrieved" if evidence.get("status") == "grounded" else "No reliable evidence; using creative-only boundary"},
            {"summary": "RAG fallback" if evidence.get("fallback") else "RAG evidence available", "evidence_status": evidence.get("status")},
        )
        skill_step = self.repository.append_step(
            session_id, user_id, "generating_product_text", "running", tool_name="select_text_skill",
            input_summary={"summary": "Selecting text writing Skill"},
        )
        skill = self.product_text_service.select_text_skill(brief)
        self.repository.finish_step(
            session_id, user_id, skill_step["id"],
            {"summary": "Text Skill selected"},
            {"summary": "Text Skill fallback" if skill.get("fallback") else "Text Skill loaded", "skill_id": skill.get("skill_id")},
        )
        generation_step = self.repository.append_step(
            session_id, user_id, "generating_product_text", "running", tool_name="generate_product_text",
            skill_id=skill.get("skill_id"), skill_version=skill.get("version"),
            input_summary={"summary": "Generating product design text"},
        )
        try:
            draft = self.product_text_service.generate(
                brief, evidence, skill, current_draft=current_draft or None, feedback=feedback,
            )
            payload = draft.model_dump()
            self.repository.finish_product_text(
                session_id, user_id, draft=payload, summary=self._product_summary(payload),
                step_id=generation_step["id"], is_revision=is_revision,
            )
        except Exception as error:
            code = getattr(error, "code", "PRODUCT_TEXT_OUTPUT_INVALID")
            message = getattr(error, "message", "Product design text could not be completed.")
            stable = {"code": code, "message": message, "retryable": getattr(error, "retryable", False), "stage": "generating_product_text"}
            self.repository.fail_step(session_id, user_id, generation_step["id"], stable)
            if is_revision:
                self.repository.return_to_text_feedback(session_id, user_id, stable)
            else:
                self.repository.mark_failed(session_id, user_id, error_code=code, error=stable)
            raise error if hasattr(error, "code") else ProductTextOutputInvalid() from error

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
        """Run only the two explicit confirmation decisions of the implemented stages."""
        if decision == "confirm_brief":
            replayed = self.repository.confirm_brief(session_id, user_id, decision_id, expected_version)
            if not replayed:
                self._generate_product_text(session_id, user_id, feedback=None, is_revision=False)
            return self._detail(session_id, user_id)
        if decision == "confirm_product_text":
            self.repository.confirm_product_text(session_id, user_id, decision_id, expected_version)
            return self._detail(session_id, user_id)
        else:
            self.repository.record_unsupported_decision(session_id, user_id, decision_id, decision, expected_status, expected_version)
            raise AgentDecisionNotSupported()
