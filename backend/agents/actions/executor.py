"""No-provider executor for approved task actions."""
from __future__ import annotations

from backend.agents.actions.policy import ActionPolicyInput, evaluate_action
from backend.domain.agent_design_domain import (
    ActionExecutorNotAvailable, ActionProposalContentIncomplete, ActionType,
    ArtifactType, canonical_json_hash,
)
from backend.services.agent_image_generation import ImageGenerationRequest


IMAGE_ACTIONS = {ActionType.GENERATE_IMAGE_FROM_CONVERSATION, ActionType.GENERATE_IMAGE_FROM_ARTIFACT, ActionType.REGENERATE_IMAGE}


class AgentActionExecutor:
    def __init__(self, repository, image_port=None): self.repository, self.image_port = repository, image_port

    def _image_snapshot(self, action):
        value=action.proposal_snapshot_json or {}
        required=("source_type","positive_prompt","negative_prompt","presentation_mode","snapshot_hash")
        if any(not value.get(key) for key in required): raise ActionProposalContentIncomplete()
        if value["source_type"] not in {"conversation_snapshot","artifact_snapshot","regeneration_snapshot"}: raise ActionProposalContentIncomplete()
        if canonical_json_hash({key:value.get(key) for key in ("source_type","source_session_id","source_task_id","source_runtime_run_id","source_message_ids","source_artifact_ids","parent_image_artifact_id","confirmed_constraints","tentative_assumptions","positive_prompt","negative_prompt","presentation_mode","provider_options")}) != value["snapshot_hash"]: raise ActionProposalContentIncomplete()
        if value["source_task_id"] != action.task_id or value["source_session_id"] != action.session_id: raise ActionProposalContentIncomplete()
        return value

    def _command(self, action):
        snapshot = action.proposal_snapshot_json or {}
        if action.action_type == ActionType.ARCHIVE_TASK:
            return {"kind": "archive_task"}
        kinds = {
            ActionType.SAVE_BRIEF: ArtifactType.BRIEF.value,
            ActionType.SAVE_DESIGN_TEXT: ArtifactType.PRODUCT_DESIGN_TEXT.value,
            ActionType.APPLY_REVISION: snapshot.get("artifact_type"),
            ActionType.BUILD_VISUAL_DIRECTION: ArtifactType.VISUAL_DIRECTION.value,
        }
        artifact_type = kinds.get(action.action_type)
        content = snapshot.get("content")
        if artifact_type not in {item.value for item in ArtifactType} or not isinstance(content, dict) or not content:
            raise ActionProposalContentIncomplete()
        command = {"kind": "artifact", "artifact_type": artifact_type, "content_json": content}
        if action.action_type == ActionType.APPLY_REVISION:
            command.update(base_artifact_id=snapshot.get("base_artifact_id"), base_content_hash=snapshot.get("base_content_hash"))
            if not command["base_artifact_id"]: raise ActionProposalContentIncomplete()
        return command

    def execute(self, user_id, action_id, *, idempotency_key, expected_action_status, expected_task_version):
        action = self.repository.get_action_any_owner(action_id, user_id)
        if expected_action_status != "approved":
            from backend.domain.agent_design_domain import ActionStateConflict
            raise ActionStateConflict()
        if action.status.value == "completed" and action.action_type not in IMAGE_ACTIONS:
            return action, True
        if action.action_type in IMAGE_ACTIONS:
            if self.image_port is None: raise ActionExecutorNotAvailable()
            snapshot=self._image_snapshot(action)
            claimed,replayed=self.repository.claim_image_action(user_id,action_id,idempotency_key=idempotency_key,expected_task_version=expected_task_version)
            if replayed: return claimed,True
            try:
                result=self.image_port.generate(ImageGenerationRequest(positive_prompt=snapshot["positive_prompt"],negative_prompt=snapshot["negative_prompt"],presentation_mode=snapshot["presentation_mode"],provider_options=snapshot.get("provider_options") or {},snapshot_hash=snapshot["snapshot_hash"]))
                self.repository.mark_image_provider_succeeded(user_id,action_id,result.provider_request_id)
                return self.repository.complete_image_action(user_id,action_id,{"image_url":result.image_url,"presentation_mode":result.presentation_mode,"provider_request_id":result.provider_request_id,"source_type":snapshot["source_type"],"snapshot_hash":snapshot["snapshot_hash"],"parent_image_artifact_id":snapshot.get("parent_image_artifact_id")})
            except Exception:
                self.repository.mark_action_failed(user_id,action_id,"IMAGE_PROVIDER_FAILED","Approved image generation did not complete.")
                raise
        conversation = self.repository.get_conversation(user_id, action.session_id)
        task = self.repository.get_task(action.task_id, user_id, action.session_id) if action.task_id else None
        artifacts = self.repository.list_artifacts(user_id, action.session_id, action.task_id)
        decision = evaluate_action(ActionPolicyInput(user_id=user_id, conversation=conversation, active_task=task,
            artifacts=tuple(artifacts), requested_action_type=action.action_type, proposal_snapshot=action.proposal_snapshot_json))
        if not decision.allowed:
            from backend.domain.agent_design_domain import ActionPolicyDenied
            raise ActionPolicyDenied(decision.reason)
        command = self._command(action)
        saved, replayed = self.repository.execute_approved_action(user_id, action_id, execution_idempotency_key=idempotency_key,
            expected_task_version=expected_task_version, command=command)
        return saved, replayed
