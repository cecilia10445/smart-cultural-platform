from datetime import datetime
import pytest

from backend.agents.actions.executor import AgentActionExecutor
from backend.domain.agent_design_domain import ActionExecutorNotAvailable, ActionProposalContentIncomplete, ActionStatus, ActionType


class Action:
    def __init__(self, action_type, status=ActionStatus.APPROVED, snapshot=None):
        self.id="a"; self.user_id="u"; self.session_id="s"; self.task_id="t"; self.action_type=action_type; self.status=status
        self.proposal_snapshot_json=snapshot or {}; self.result_json={"created_artifact_ids":["x"]}


class Repo:
    def __init__(self, action): self.action=action
    def get_action_any_owner(self, *_): return self.action


def test_image_actions_are_not_claimed_or_failed():
    with pytest.raises(ActionExecutorNotAvailable):
        AgentActionExecutor(Repo(Action(ActionType.GENERATE_IMAGE_FROM_CONVERSATION))).execute("u", "a", idempotency_key="k", expected_action_status="approved", expected_task_version=1)


def test_completed_action_replays_before_policy_or_provider_work():
    action, saved = AgentActionExecutor(Repo(Action(ActionType.ARCHIVE_TASK, ActionStatus.COMPLETED))).execute("u", "a", idempotency_key="k", expected_action_status="approved", expected_task_version=1)
    assert saved and action.id == "a"


def test_artifact_commands_require_frozen_complete_content():
    executor = AgentActionExecutor(Repo(Action(ActionType.SAVE_BRIEF)))
    with pytest.raises(ActionProposalContentIncomplete): executor._command(executor.repository.action)
    command = AgentActionExecutor(Repo(Action(ActionType.SAVE_BRIEF, snapshot={"content":{"title":"x"}})))._command(Repo(Action(ActionType.SAVE_BRIEF, snapshot={"content":{"title":"x"}})).action)
    assert command["artifact_type"] == "brief"
