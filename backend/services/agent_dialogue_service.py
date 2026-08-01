"""Application service for the round-one Agent dialogue state machine."""

from __future__ import annotations

import json
import time
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
    AgentImageGenerationFailed,
    AgentImagePersistenceFailed,
    TextRevisionLimitReached,
    project_agent_session_detail,
    project_agent_session_list_item,
)
from backend.services.agent_dialogue_repository import AgentDialogueRepository
from backend.services.agent_brief_agent import BriefAgent
from backend.services.agent_product_text import ProductTextService
from backend.services.agent_visual_prompt import build_image_prompt_package, load_visual_skill
from backend.services.agent_image_generation import AgentImageGenerationService
from backend.services.aigc_service import AIGCServiceError


class AgentDialogueService:
    """Owns owner-scoped state changes and invokes bounded stage adapters."""

    def __init__(
        self, repository: AgentDialogueRepository, brief_agent: BriefAgent | None = None,
        product_text_service: ProductTextService | None = None, visual_prompt_builder=build_image_prompt_package,
        visual_skill_loader=load_visual_skill, image_generation_service: AgentImageGenerationService | None = None,
    ):
        self.repository = repository
        self.brief_agent = brief_agent or BriefAgent()
        self.product_text_service = product_text_service or ProductTextService()
        self.visual_prompt_builder = visual_prompt_builder
        self.visual_skill_loader = visual_skill_loader
        self.image_generation_service = image_generation_service or AgentImageGenerationService()

    def _detail(self, session_id: str, user_id: str) -> AgentSessionDetailResponse:
        session, messages, steps = self.repository.get_detail_rows(session_id, user_id)
        return project_agent_session_detail(session, messages, steps)

    def create_session(self, user_id: str) -> AgentSessionDetailResponse:
        session = self.repository.create_session(user_id)
        return project_agent_session_detail(session, [], [])

    def get_session(self, session_id: str, user_id: str) -> AgentSessionDetailResponse:
        return self._detail(session_id, user_id)

    def list_sessions(self, user_id: str):
        return [project_agent_session_list_item(row) for row in self.repository.list_sessions(user_id)]

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

    def _build_visual_prompt(self, session_id: str, user_id: str) -> None:
        """Load one visual Skill and build a package outside persistence transactions."""
        session = self.repository.get_session(session_id, user_id)
        brief_record = self._json_object(session.get("brief_json"))
        brief = self._json_object(brief_record.get("normalized_brief"))
        design = self._json_object(session.get("confirmed_text_json"))
        if not brief or not design:
            raise AgentSessionStateConflict()
        skill_step = self.repository.append_step(
            session_id, user_id, "building_visual_prompt", "running", tool_name="select_visual_skill",
            input_summary={"summary": "Selecting visual design Skill"},
        )
        skill = self.visual_skill_loader(brief, design)
        self.repository.finish_step(
            session_id, user_id, skill_step["id"], {"summary": "Visual Skill selected"},
            {"summary": "Visual Skill fallback" if skill.get("fallback") else "Visual Skill loaded", "skill_id": skill.get("skill_id")},
        )
        build_step = self.repository.append_step(
            session_id, user_id, "building_visual_prompt", "running", tool_name="build_visual_prompt",
            skill_id=skill.get("skill_id"), skill_version=skill.get("version"), input_summary={"summary": "Building visual direction"},
        )
        try:
            package = self.visual_prompt_builder(brief, design, design.get("evidence", []), skill)
            payload = package.model_dump()
            self.repository.finish_visual_prompt(
                session_id, user_id, package=payload, summary=package.user_facing_direction, step_id=build_step["id"],
            )
        except Exception as error:
            stable = {"code": "VISUAL_PROMPT_OUTPUT_INVALID", "message": "Visual direction could not be prepared.",
                      "retryable": False, "stage": "building_visual_prompt"}
            self.repository.fail_step(session_id, user_id, build_step["id"], stable)
            self.repository.mark_failed(session_id, user_id, error_code=stable["code"], error=stable)
            raise ProductTextOutputInvalid() from error

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
            replayed = self.repository.confirm_product_text(session_id, user_id, decision_id, expected_version)
            if not replayed:
                self._build_visual_prompt(session_id, user_id)
            return self._detail(session_id, user_id)
        if decision == "confirm_image_generation":
            replayed = self.repository.confirm_image_generation(session_id, user_id, decision_id, expected_version)
            if not replayed:
                self._generate_final_image(session_id, user_id)
            return self._detail(session_id, user_id)
        else:
            self.repository.record_unsupported_decision(session_id, user_id, decision_id, decision, expected_status, expected_version)
            raise AgentDecisionNotSupported()

    def _generate_final_image(self, session_id: str, user_id: str) -> None:
        """Provider work occurs after the claim transaction, never inside it."""
        session = self.repository.get_session(session_id, user_id)
        brief_record = self._json_object(session.get("brief_json"))
        brief = self._json_object(brief_record.get("normalized_brief"))
        design = self._json_object(session.get("confirmed_text_json"))
        package = self._json_object(session.get("image_prompt_json"))
        if not brief or not design or not package:
            raise AgentSessionStateConflict()
        step = self.repository.append_step(session_id, user_id, "generating_image", "running", tool_name="generate_product_image",
                                           skill_id=package.get("selected_visual_skill"), input_summary={"summary": "Generating confirmed final image"})
        started = time.perf_counter()
        image_url = None
        try:
            generated = self.image_generation_service.generate(package)
            image_url = generated.get("image_url") if isinstance(generated, dict) else None
            if not isinstance(image_url, str) or not image_url:
                raise ValueError("IMAGE_RESULT_INVALID")
            generation_time = round(time.perf_counter() - started, 2)
            title = str(design.get("product_name") or brief.get("product_type") or "文创产品")[:255]
            content = self._product_summary(design)
            final_payload = {
                "agent_session_id": session_id, "product_name": title, "image_url": image_url,
                "generation_time": generation_time, "evidence_status": design.get("evidence_status"),
                "used_source_ids": [item for item in design.get("used_source_ids", []) if isinstance(item, str)],
                "selected_text_skill": design.get("selected_text_skill"), "selected_visual_skill": package.get("selected_visual_skill"),
                "product_design_summary": content[:4000],
                "visual_direction": {key: package.get(key) for key in ("product_form", "materials", "color_plan", "composition", "scene", "presentation_mode")},
            }
            self.repository.finish_image_generation(session_id, user_id, step_id=step["id"], image_url=image_url,
                                                    response_payload=final_payload, brief=brief, title=title,
                                                    content=content, generation_time=generation_time)
        except AIGCServiceError as error:
            stable = {"code": "AGENT_IMAGE_GENERATION_FAILED", "message": "Final image generation was unavailable.",
                      "retryable": error.retryable, "stage": "generating_image"}
            self.repository.record_image_persistence_failure(session_id, user_id, step_id=step["id"], error=stable)
            raise AgentImageGenerationFailed() from error
        except Exception as error:
            stable = {"code": "AGENT_IMAGE_PERSISTENCE_FAILED", "message": "The generated image could not be finalized; it will not be generated again automatically.",
                      "retryable": False, "stage": "generating_image"}
            self.repository.record_image_persistence_failure(session_id, user_id, step_id=step["id"], error=stable, image_url=image_url)
            raise AgentImagePersistenceFailed() from error
