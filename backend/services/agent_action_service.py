"""Application service for explicit, non-executing action approval."""
from __future__ import annotations

from typing import Any

from backend.agents.actions.policy import ActionPolicyInput, available_actions, evaluate_action
from backend.agents.design_conversation.outputs import ConversationReply
from backend.domain.agent_design_domain import (
    ActionPolicyDenied, ActionReferenceConflict, ActionType, ArtifactRecord,
    ArtifactStatus, ArtifactType, DesignTaskRecord, canonical_json_hash,
    project_legacy_session,
)
from backend.services.agent_design_domain_repository import AgentDesignDomainRepository
from backend.agents.actions.executor import AgentActionExecutor



class AgentActionService:
    def __init__(self, repository: AgentDesignDomainRepository, image_port=None):
        self.repository, self.image_port = repository, image_port

    @staticmethod
    def _safe_action(action) -> dict[str, Any]:
        return {
            "id": action.id, "action_type": action.action_type, "status": action.status,
            "task_id": action.task_id, "scope_type": action.scope_type, "safe_summary": (action.proposal_snapshot_json or {}).get("summary", "Explicit design action"),
            "requires_confirmation": action.status.value == "requested", "created_at": action.created_at,
            "approved_at": action.approved_at,
        }

    def task_view(self, user_id: str, session_id: str, task_id: str) -> DesignTaskRecord:
        return self.repository.get_task(task_id, user_id, session_id)

    def available(self, user_id: str, session_id: str) -> list[dict[str, Any]]:
        conversation = self.repository.get_conversation(user_id, session_id)
        task = self.repository.get_active_task(user_id, session_id)
        artifacts: list[ArtifactRecord] = self.repository.list_artifacts(user_id, session_id, task.id if task else None)
        pending = self.repository.list_actions(user_id, session_id, task.id if task else None)
        return available_actions(conversation, task, artifacts, pending)

    @staticmethod
    def _generation_snapshot(*, session_id: str, task_id: str | None, run_id: str, reply: ConversationReply,
                             messages: list[dict[str, Any]]) -> dict[str, Any]:
        """Build a reviewable image package from verified Runtime output.

        This deliberately represents a conversation snapshot rather than
        inventing a Brief.  The model must already have emitted the closed
        ActionType; this helper never infers an action from user keywords.
        """
        user_messages = [str(row.get("content_text") or "").strip() for row in messages if row.get("role") == "user"]
        user_messages = [value for value in user_messages if value]
        latest_request = user_messages[-1] if user_messages else "当前对话中的设计需求"
        presentation_mode = "three_view" if "三视图" in latest_request else "single_product_render"
        snapshot = {
            "source_type": "conversation_snapshot",
            "source_session_id": session_id,
            "source_task_id": task_id,
            "source_runtime_run_id": run_id,
            "source_message_ids": [str(row["id"]) for row in messages if row.get("id")],
            "source_artifact_ids": [],
            "parent_image_artifact_id": None,
            "confirmed_constraints": [latest_request[:500]],
            "tentative_assumptions": ["按当前对话生成一版试稿；这不会保存为正式 Brief。"],
            # Kept in the frozen server snapshot only.  The display DTO below
            # intentionally exposes constraints and assumptions, not prompts.
            "positive_prompt": f"文化创意产品设计。用户需求：{latest_request}。设计说明：{reply.message[:1200]}",
            "negative_prompt": "watermark, unreadable text, low resolution, distorted product",
            "presentation_mode": presentation_mode,
            "provider_options": {},
            "summary": reply.business_action.reason_summary if reply.business_action else "根据当前对话生成一版试稿",
            "proposal_kind": ActionType.GENERATE_IMAGE_FROM_CONVERSATION.value,
            "output_origin": reply.output_origin,
        }
        snapshot["snapshot_hash"] = canonical_json_hash({key: snapshot.get(key) for key in (
            "source_type", "source_session_id", "source_task_id", "source_runtime_run_id", "source_message_ids",
            "source_artifact_ids", "parent_image_artifact_id", "confirmed_constraints", "tentative_assumptions",
            "positive_prompt", "negative_prompt", "presentation_mode", "provider_options",
        )})
        return snapshot

    def _runtime_proposal(self, user_id: str | dict[str, Any], session_id: str | ActionType,
                          run: dict[str, Any] | None = None, action_type: ActionType | None = None) -> dict[str, Any]:
        # Keep the internal two-argument form usable by existing callers for
        # non-image proposals.  Conversation image snapshots require the
        # owner/session context supplied by the public service methods.
        legacy_call = run is None and action_type is None
        if legacy_call:
            run, action_type = user_id, session_id
            user_id, session_id = "", ""
        assert isinstance(run, dict) and isinstance(action_type, ActionType)
        if run.get("status") != "completed":
            raise ActionReferenceConflict("Runtime proposal has not completed.")
        raw = run.get("final_output_json")
        if not isinstance(raw, dict):
            raise ActionReferenceConflict("Runtime result has no valid action proposal.")
        try:
            reply = ConversationReply.model_validate(raw)
        except Exception as exc:
            raise ActionReferenceConflict("Runtime result has no valid action proposal.") from exc
        if reply.output_origin not in {"provider", "provider_repair"}:
            raise ActionReferenceConflict("Only verified provider proposals may request a design action.")
        if reply.business_action is not None:
            if not isinstance(reply.business_action.action, ActionType) or reply.business_action.action != action_type:
                raise ActionReferenceConflict("Requested action does not match the runtime proposal.")
            snapshot = dict(reply.business_action.snapshot or {})
            snapshot.update({"summary": reply.business_action.reason_summary,
                             "proposal_kind": action_type.value, "output_origin": reply.output_origin})
            if action_type is ActionType.GENERATE_IMAGE_FROM_CONVERSATION:
                if legacy_call:
                    raise ActionReferenceConflict("Conversation snapshot requires owner-scoped context.")
                messages = self.repository.get_runtime_message_snapshot(user_id, session_id, run.get("task_id"))
                return self._generation_snapshot(session_id=session_id, task_id=run.get("task_id"), run_id=str(run["id"]),
                                                 reply=reply, messages=messages)
            snapshot.setdefault("source_type", "runtime_proposal")
            snapshot.setdefault("tentative_assumptions", [])
            return snapshot
        # A typed, unsaved artifact can only back its corresponding save command.
        proposal = reply.artifact_proposal
        expected = {ActionType.SAVE_BRIEF: "brief", ActionType.SAVE_DESIGN_TEXT: "product_design_text"}
        if proposal is None or expected.get(action_type) != proposal.kind:
            raise ActionReferenceConflict("Requested action does not match the runtime proposal.")
        kind = "brief" if proposal.kind == "brief" else "product_design_text"
        return {"source_type": "runtime_proposal", "summary": proposal.summary, "proposal_kind": kind,
                "content": proposal.content, "tentative_assumptions": proposal.assumptions,
                "output_origin": reply.output_origin}

    def runtime_action_proposal(self, user_id: str, session_id: str, run_id: str, action_type: ActionType) -> dict[str, Any]:
        """Return a display-safe, server-derived reference for a requested command.

        The digest is calculated from the complete frozen proposal; prompt text
        and provider options deliberately never cross this HTTP boundary.
        """
        run = self.repository.get_runtime_run_for_action(user_id, session_id, run_id)
        snapshot = self._runtime_proposal(user_id, session_id, run, action_type)
        display = {
            "source_type": snapshot.get("source_type"),
            "safe_summary": snapshot.get("summary"),
            "confirmed_constraints": snapshot.get("confirmed_constraints") or [],
            "tentative_assumptions": snapshot.get("tentative_assumptions") or [],
            "presentation_mode": snapshot.get("presentation_mode"),
        }
        return {"source_runtime_run_id": run_id, "action_type": action_type.value,
                "source_proposal_digest": canonical_json_hash({"action_type": action_type.value, "proposal": snapshot}),
                "display": display}

    def request_action(self, user_id: str, session_id: str, task_id: str | None, *, action_type: ActionType, idempotency_key: str,
                       source_runtime_run_id: str, source_proposal_digest: str, expected_task_version: int | None):
        conversation = self.repository.get_conversation(user_id, session_id)
        task = self.repository.get_task(task_id, user_id, session_id) if task_id else None
        active = self.repository.get_active_task(user_id, session_id)
        if task is not None and (active is None or active.id != task.id):
            raise ActionReferenceConflict("Select this design task before requesting an action.")
        run = self.repository.get_runtime_run_for_action(user_id, session_id, source_runtime_run_id)
        if run.get("task_id") != task_id:
            raise ActionReferenceConflict("Runtime proposal belongs to another design task.")
        snapshot = self._runtime_proposal(user_id, session_id, run, action_type)
        digest = canonical_json_hash({"action_type": action_type.value, "proposal": snapshot})
        if digest != source_proposal_digest:
            raise ActionReferenceConflict("Runtime proposal digest does not match.")
        artifacts = self.repository.list_artifacts(user_id, session_id, task_id)
        decision = evaluate_action(ActionPolicyInput(user_id=user_id, conversation=conversation, active_task=task,
            artifacts=tuple(artifacts), requested_action_type=action_type, proposal_snapshot=snapshot, source_runtime_run=run))
        if not decision.allowed: raise ActionPolicyDenied(decision.reason)
        action, replayed = self.repository.insert_action_request(user_id, session_id, task_id, action_type=action_type,
            idempotency_key=idempotency_key, expected_task_version=expected_task_version, source_runtime_run_id=source_runtime_run_id,
            proposal_snapshot_json=snapshot)
        return self._safe_action(action), replayed

    @staticmethod
    def _approval_snapshot(value: dict[str, Any] | None) -> dict[str, Any]:
        source = value or {}
        allowed = ("accepted_tentative_assumptions", "presentation_mode", "cost_confirmation", "selected_artifact_ids", "user_note")
        return {key: source[key] for key in allowed if key in source}

    def approve(self, user_id: str, action_id: str, *, expected_action_status: str, expected_task_version: int | None,
                idempotency_key: str, approval_snapshot: dict[str, Any] | None):
        # Find by owner only; no guessed action id can cross an ownership boundary.
        action = self.repository.get_action_any_owner(action_id, user_id)
        if expected_action_status != "requested": raise ActionReferenceConflict("Expected action status must be requested.")
        conversation = self.repository.get_conversation(user_id, action.session_id)
        task = self.repository.get_task(action.task_id, user_id, action.session_id) if action.task_id else None
        active = self.repository.get_active_task(user_id, action.session_id)
        if task is not None and (active is None or active.id != task.id): raise ActionReferenceConflict("This action is no longer on the active design task.")
        artifacts = self.repository.list_artifacts(user_id, action.session_id, action.task_id)
        decision = evaluate_action(ActionPolicyInput(user_id=user_id, conversation=conversation, active_task=task,
            artifacts=tuple(artifacts), requested_action_type=action.action_type, proposal_snapshot=action.proposal_snapshot_json))
        if not decision.allowed: raise ActionPolicyDenied(decision.reason)
        snapshot = self._approval_snapshot(approval_snapshot)
        if action.action_type in {ActionType.GENERATE_IMAGE_FROM_CONVERSATION, ActionType.GENERATE_IMAGE_FROM_ARTIFACT, ActionType.REGENERATE_IMAGE} and snapshot.get("cost_confirmation") is not True:
            raise ActionPolicyDenied("Image generation requires explicit cost confirmation.")
        saved, replayed = self.repository.approve_action(user_id, action.session_id, action.task_id, action.id,
            expected_task_version=expected_task_version, approval_idempotency_key=idempotency_key, approval_snapshot_json=snapshot)
        return self._safe_action(saved), replayed

    def reject(self, user_id: str, action_id: str, *, idempotency_key: str, reason: str | None):
        action = self.repository.get_action_any_owner(action_id, user_id)
        saved, replayed = self.repository.reject_action(user_id, action.session_id, action.task_id, action.id,
            rejection_idempotency_key=idempotency_key, reason=reason)
        return self._safe_action(saved), replayed

    def execute(self, user_id, action_id, *, idempotency_key, expected_action_status, expected_task_version):
        action, replayed = AgentActionExecutor(self.repository, image_port=self.image_port).execute(user_id, action_id, idempotency_key=idempotency_key,
            expected_action_status=expected_action_status, expected_task_version=expected_task_version)
        task = self.repository.get_task(action.task_id, user_id, action.session_id) if action.task_id else None
        return {"action": self._safe_action(action), "created_artifact_ids": (action.result_json or {}).get("created_artifact_ids", []),
                "superseded_artifact_ids": (action.result_json or {}).get("superseded_artifact_ids", []), "task": task.model_dump() if task else None}, replayed

    @staticmethod
    def _safe_artifact(item):
        return {"id": item.id, "task_id": item.task_id, "scope_type": item.scope_type, "artifact_type": item.artifact_type, "status": item.status,
                "version_number": item.version_number, "parent_artifact_id": item.parent_artifact_id, "safe_content": item.content_json,
                "origin": item.origin, "created_at": item.created_at, "confirmed_at": item.confirmed_at,
                "superseded_at": item.superseded_at, "generation_log_id": item.generation_log_id}

    def artifacts(self, user_id, session_id, task_id, *, artifact_type=None, status=None, include_legacy=False):
        native = self.repository.list_artifacts(user_id, session_id, task_id)
        if artifact_type: native = [item for item in native if item.artifact_type.value == artifact_type]
        if status: native = [item for item in native if item.status.value == status]
        result = [self._safe_artifact(item) for item in native]
        if include_legacy:
            projection = project_legacy_session(self.repository.get_session(session_id, user_id))
            for item in projection.artifacts:
                result.append({"id": item.id, "task_id": item.task_id, "artifact_type": item.artifact_type, "status": item.status,
                               "version_number": 0, "parent_artifact_id": None, "safe_content": item.content_json,
                               "origin": item.origin, "created_at": None, "confirmed_at": None, "superseded_at": None,
                               "generation_log_id": item.generation_log_id, "read_only": True, "materialized": False})
        return result

    @staticmethod
    def _history_artifact(item: ArtifactRecord) -> dict[str, Any]:
        """A compact archive representation; prompts and provider payloads stay private."""
        content = item.content_json if isinstance(item.content_json, dict) else {}
        summary = next((content.get(key) for key in ("summary", "title", "product_name", "design_goal", "concept")
                        if isinstance(content.get(key), str) and content.get(key).strip()), None)
        return {
            "id": item.id,
            "artifact_type": item.artifact_type.value,
            "status": item.status.value,
            "version_number": item.version_number,
            "parent_artifact_id": item.parent_artifact_id,
            "generation_log_id": item.generation_log_id,
            "summary": summary[:240] if isinstance(summary, str) else None,
            "origin": item.origin.value,
            "created_at": item.created_at,
            "confirmed_at": item.confirmed_at,
        }

    @staticmethod
    def _safe_generation_snapshot(snapshot: dict[str, Any] | None, approval: dict[str, Any] | None) -> dict[str, Any]:
        source = snapshot if isinstance(snapshot, dict) else {}
        confirmed = source.get("confirmed_constraints")
        tentative = source.get("tentative_assumptions")
        message_ids = source.get("source_message_ids")
        artifact_ids = source.get("source_artifact_ids")
        return {
            "source_type": source.get("source_type") if isinstance(source.get("source_type"), str) else None,
            "confirmed_constraints": [value[:240] for value in confirmed if isinstance(value, str)][:20] if isinstance(confirmed, list) else [],
            "tentative_assumptions": [value[:240] for value in tentative if isinstance(value, str)][:20] if isinstance(tentative, list) else [],
            "presentation_mode": source.get("presentation_mode") if isinstance(source.get("presentation_mode"), str) else None,
            "source_message_count": len(message_ids) if isinstance(message_ids, list) else 0,
            "source_artifact_count": len(artifact_ids) if isinstance(artifact_ids, list) else 0,
            "cost_confirmed": bool((approval or {}).get("cost_confirmation")),
        }

    def generation_history_detail(self, user_id: str, generation_log_id: int) -> dict[str, Any]:
        """Return a read-only, owner-scoped view for Agent image history.

        The historical view deliberately projects only archive-safe metadata.
        It does not return prompts, provider options, raw observations, or the
        provider response stored behind a generation log.
        """
        rows = self.repository.get_generation_history_rows(user_id, generation_log_id)
        log = rows["log"]
        action = rows["action"]
        image = rows["image_artifact"]
        legacy_session = rows["legacy_session"]
        generation_log = {
            "id": int(log["id"]),
            "created_at": log.get("timestamp"),
            "image_url": log.get("image_url") if isinstance(log.get("image_url"), str) else None,
            "title": log.get("title") if isinstance(log.get("title"), str) else None,
            "generation_kind": log.get("generation_kind") if isinstance(log.get("generation_kind"), str) else "unknown",
        }

        if action is not None and image is not None:
            if (action.session_id, action.scope_key) != (image.session_id, image.scope_key):
                # A corrupted cross-task relation must not become a blended
                # archive view, even when both rows belong to the same owner.
                from backend.domain.agent_design_domain import AgentGenerationHistoryNotFound
                raise AgentGenerationHistoryNotFound()
            task = self.repository.get_task(action.task_id, user_id, action.session_id) if action.task_id else None
            artifacts = self.repository.list_artifacts(user_id, action.session_id, action.task_id)
            parent = next((item for item in artifacts if item.id == image.parent_artifact_id), None)
            related = [self._history_artifact(item) for item in artifacts
                       if item.status is ArtifactStatus.CONFIRMED and item.artifact_type is not ArtifactType.GENERATED_IMAGE]
            return {
                "kind": "agent_artifact_image",
                "read_only": True,
                "generation_log": generation_log,
                "image_artifact": self._history_artifact(image),
                "source_action": {
                    "id": action.id, "action_type": action.action_type.value, "status": action.status.value,
                    "safe_summary": (action.proposal_snapshot_json or {}).get("summary", "Approved image action"),
                    "created_at": action.created_at, "approved_at": action.approved_at, "completed_at": action.completed_at,
                },
                "source_task": ({"id": task.id, "title": task.title, "status": task.status.value, "origin": task.origin.value, "version": task.version}
                                if task is not None else None),
                "related_artifacts": related,
                "generation_snapshot": self._safe_generation_snapshot(action.proposal_snapshot_json, action.approval_snapshot_json),
                "version_lineage": {"version_number": image.version_number, "parent_artifact_id": image.parent_artifact_id,
                                    "parent_version_number": parent.version_number if parent is not None else None},
                "continue_design": {"session_id": action.session_id, "task_id": task.id if task is not None else None,
                                    "available": task is None or task.status.value != "closed"},
            }

        if legacy_session is not None:
            projection = project_legacy_session(legacy_session)
            return {
                "kind": "legacy_agent_generation",
                "read_only": True,
                "generation_log": generation_log,
                "image_artifact": None,
                "source_action": None,
                "source_task": {"id": projection.task.id, "title": projection.task.title, "status": "legacy_read_only", "origin": "legacy_projection", "version": None},
                "related_artifacts": [
                    {"id": item.id, "artifact_type": item.artifact_type.value, "status": "legacy_read_only", "version_number": 0,
                     "parent_artifact_id": None, "generation_log_id": item.generation_log_id, "summary": None,
                     "origin": item.origin.value, "created_at": None, "confirmed_at": None}
                    for item in projection.artifacts
                ],
                "generation_snapshot": {"source_type": "legacy_session", "confirmed_constraints": [], "tentative_assumptions": [],
                                        "presentation_mode": None, "source_message_count": 0, "source_artifact_count": 0, "cost_confirmed": None},
                "version_lineage": {"version_number": None, "parent_artifact_id": None, "parent_version_number": None},
                "continue_design": {"session_id": legacy_session["id"], "task_id": None, "available": True, "legacy": True},
            }

        from backend.domain.agent_design_domain import AgentGenerationHistoryNotFound
        raise AgentGenerationHistoryNotFound()
