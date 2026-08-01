"""Application service for explicit, non-executing action approval."""
from __future__ import annotations

from typing import Any

from backend.agents.actions.policy import ActionPolicyInput, available_actions, evaluate_action
from backend.agents.design_conversation.outputs import ConversationReply
from backend.domain.agent_design_domain import (
    ActionPolicyDenied, ActionReferenceConflict, ActionType, ArtifactRecord,
    DesignTaskRecord, canonical_json_hash,
)
from backend.services.agent_design_domain_repository import AgentDesignDomainRepository
from backend.agents.actions.executor import AgentActionExecutor
from backend.domain.agent_design_domain import project_legacy_session


class AgentActionService:
    def __init__(self, repository: AgentDesignDomainRepository, image_port=None):
        self.repository, self.image_port = repository, image_port

    @staticmethod
    def _safe_action(action) -> dict[str, Any]:
        return {
            "id": action.id, "action_type": action.action_type, "status": action.status,
            "task_id": action.task_id, "safe_summary": (action.proposal_snapshot_json or {}).get("summary", "Explicit design action"),
            "requires_confirmation": action.status.value == "requested", "created_at": action.created_at,
            "approved_at": action.approved_at,
        }

    def task_view(self, user_id: str, session_id: str, task_id: str) -> DesignTaskRecord:
        return self.repository.get_task(task_id, user_id, session_id)

    def available(self, user_id: str, session_id: str) -> list[dict[str, Any]]:
        conversation = self.repository.get_conversation(user_id, session_id)
        task = self.repository.get_active_task(user_id, session_id)
        artifacts: list[ArtifactRecord] = self.repository.list_artifacts(user_id, session_id, task.id) if task else []
        pending = self.repository.list_actions(user_id, session_id, task.id) if task else []
        return available_actions(conversation, task, artifacts, pending)

    def _runtime_proposal(self, run: dict[str, Any], action_type: ActionType) -> dict[str, Any]:
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
            return {"source_type": "runtime_proposal", "summary": reply.business_action.reason_summary,
                    "proposal_kind": action_type.value, "output_origin": reply.output_origin,
                    "tentative_assumptions": []}
        # A typed, unsaved artifact can only back its corresponding save command.
        proposal = reply.artifact_proposal
        expected = {ActionType.SAVE_BRIEF: "brief", ActionType.SAVE_DESIGN_TEXT: "product_design_text"}
        if proposal is None or expected.get(action_type) != proposal.kind:
            raise ActionReferenceConflict("Requested action does not match the runtime proposal.")
        kind = "brief" if proposal.kind == "brief" else "product_design_text"
        return {"source_type": "runtime_proposal", "summary": proposal.summary, "proposal_kind": kind,
                "content": proposal.content, "tentative_assumptions": proposal.assumptions,
                "output_origin": reply.output_origin}

    def request_action(self, user_id: str, session_id: str, task_id: str, *, action_type: ActionType, idempotency_key: str,
                       source_runtime_run_id: str, source_proposal_digest: str, expected_task_version: int | None):
        conversation = self.repository.get_conversation(user_id, session_id)
        task = self.repository.get_task(task_id, user_id, session_id)
        active = self.repository.get_active_task(user_id, session_id)
        if active is None or active.id != task.id:
            raise ActionReferenceConflict("Select this design task before requesting an action.")
        run = self.repository.get_runtime_run_for_action(user_id, session_id, source_runtime_run_id)
        if run.get("task_id") and run["task_id"] != task_id:
            raise ActionReferenceConflict("Runtime proposal belongs to another design task.")
        snapshot = self._runtime_proposal(run, action_type)
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
        task = self.repository.get_task(action.task_id, user_id, action.session_id)
        active = self.repository.get_active_task(user_id, action.session_id)
        if active is None or active.id != task.id: raise ActionReferenceConflict("This action is no longer on the active design task.")
        artifacts = self.repository.list_artifacts(user_id, action.session_id, task.id)
        decision = evaluate_action(ActionPolicyInput(user_id=user_id, conversation=conversation, active_task=task,
            artifacts=tuple(artifacts), requested_action_type=action.action_type, proposal_snapshot=action.proposal_snapshot_json))
        if not decision.allowed: raise ActionPolicyDenied(decision.reason)
        snapshot = self._approval_snapshot(approval_snapshot)
        if action.action_type in {ActionType.GENERATE_IMAGE_FROM_CONVERSATION, ActionType.GENERATE_IMAGE_FROM_ARTIFACT, ActionType.REGENERATE_IMAGE} and snapshot.get("cost_confirmation") is not True:
            raise ActionPolicyDenied("Image generation requires explicit cost confirmation.")
        saved, replayed = self.repository.approve_action(user_id, action.session_id, task.id, action.id,
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
        task = self.repository.get_task(action.task_id, user_id, action.session_id)
        return {"action": self._safe_action(action), "created_artifact_ids": (action.result_json or {}).get("created_artifact_ids", []),
                "superseded_artifact_ids": (action.result_json or {}).get("superseded_artifact_ids", []), "task": task.model_dump()}, replayed

    @staticmethod
    def _safe_artifact(item):
        return {"id": item.id, "task_id": item.task_id, "artifact_type": item.artifact_type, "status": item.status,
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
