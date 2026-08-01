"""No-provider executor for approved task actions."""
from __future__ import annotations

from backend.agents.actions.policy import ActionPolicyInput, evaluate_action
from backend.domain.agent_design_domain import (
    ActionExecutorNotAvailable, ActionProposalContentIncomplete, ActionType,
    ArtifactType, canonical_json_hash,
)


IMAGE_ACTIONS = {ActionType.GENERATE_IMAGE_FROM_CONVERSATION, ActionType.GENERATE_IMAGE_FROM_ARTIFACT, ActionType.REGENERATE_IMAGE}


class AgentActionExecutor:
    def __init__(self, repository): self.repository = repository

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
        if action.status.value == "completed":
            return action, True
        if action.action_type in IMAGE_ACTIONS:
            raise ActionExecutorNotAvailable()
        conversation = self.repository.get_conversation(user_id, action.session_id)
        task = self.repository.get_task(action.task_id, user_id, action.session_id)
        artifacts = self.repository.list_artifacts(user_id, action.session_id, task.id)
        decision = evaluate_action(ActionPolicyInput(user_id=user_id, conversation=conversation, active_task=task,
            artifacts=tuple(artifacts), requested_action_type=action.action_type, proposal_snapshot=action.proposal_snapshot_json))
        if not decision.allowed:
            from backend.domain.agent_design_domain import ActionPolicyDenied
            raise ActionPolicyDenied(decision.reason)
        command = self._command(action)
        saved, replayed = self.repository.execute_approved_action(user_id, action_id, execution_idempotency_key=idempotency_key,
            expected_task_version=expected_task_version, command=command)
        return saved, replayed
