from backend.agents.actions.executor import AgentActionExecutor
from backend.domain.agent_design_domain import ActionStatus, ActionType, canonical_json_hash
from backend.services.agent_image_generation import ImageGenerationResult


def snapshot():
    value={"source_type":"conversation_snapshot","source_session_id":"s","source_task_id":"t","source_runtime_run_id":"r","source_message_ids":["m"],"source_artifact_ids":[],"parent_image_artifact_id":None,"confirmed_constraints":["c"],"tentative_assumptions":["a"],"positive_prompt":"p","negative_prompt":"n","presentation_mode":"single_hero","provider_options":{}}
    value["snapshot_hash"]=canonical_json_hash(value)
    return value

class Action:
    id="a"; user_id="u"; session_id="s"; task_id="t"; action_type=ActionType.GENERATE_IMAGE_FROM_CONVERSATION; status=ActionStatus.APPROVED
    proposal_snapshot_json=snapshot(); result_json={}

class Port:
    def __init__(self): self.call_count=0
    def generate(self, request): self.call_count+=1; return ImageGenerationResult("mock://generated/a",request.presentation_mode,"mock-request-a")

class Repo:
    def __init__(self): self.action=Action(); self.claimed=0
    def get_action_any_owner(self,*_): return self.action
    def claim_image_action(self,*_,**__): self.claimed+=1; return self.action,False
    def mark_image_provider_succeeded(self,*_): pass
    def complete_image_action(self,*_): self.action.status=ActionStatus.COMPLETED; return self.action,False
    def mark_action_failed(self,*_): self.action.status=ActionStatus.FAILED

def test_fake_image_port_is_called_once_with_frozen_snapshot():
    repo,port=Repo(),Port()
    action,replayed=AgentActionExecutor(repo,port).execute("u","a",idempotency_key="x",expected_action_status="approved",expected_task_version=1)
    assert port.call_count == 1 and not replayed and action.status is ActionStatus.COMPLETED
