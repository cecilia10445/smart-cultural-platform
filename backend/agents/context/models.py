from __future__ import annotations
from enum import Enum
from pydantic import BaseModel, ConfigDict, Field

class FactSource(str, Enum): USER_CONFIRMED='USER_CONFIRMED'; BUSINESS_CONFIRMED='BUSINESS_CONFIRMED'; TOOL_OBSERVED='TOOL_OBSERVED'; MODEL_INFERRED='MODEL_INFERRED'
class ContextFact(BaseModel):
    model_config=ConfigDict(extra='forbid')
    value:str; source_type:FactSource; source_message_ids:list[str]=Field(default_factory=list); source_tool_call_ids:list[str]=Field(default_factory=list); confidence:float=Field(ge=0,le=1)
class ContextSummaryV2(BaseModel):
    model_config=ConfigDict(extra='forbid')
    schema_version:str='context-summary-v2'; session_id:str; source_message_start_id:str|None=None; source_message_end_id:str|None=None; source_message_count:int=0
    user_goal:ContextFact|None=None; confirmed_constraints:list[ContextFact]=Field(default_factory=list); tentative_preferences:list[ContextFact]=Field(default_factory=list); design_decisions:list[ContextFact]=Field(default_factory=list); rejected_directions:list[ContextFact]=Field(default_factory=list)
    current_artifacts:list[dict]=Field(default_factory=list); cultural_evidence_refs:list[dict]=Field(default_factory=list); loaded_skill_refs:list[dict]=Field(default_factory=list); unresolved_questions:list[ContextFact]=Field(default_factory=list); pending_actions:list[str]=Field(default_factory=list); important_failures:list[str]=Field(default_factory=list); conversation_summary:str=''

class ContextValidationScope(BaseModel):
    """The closed world a model generated summary is allowed to refer to."""
    model_config = ConfigDict(extra="forbid")
    session_id: str
    message_ids: set[str] = Field(default_factory=set)
    source_ids: set[str] = Field(default_factory=set)
    skill_ids: set[str] = Field(default_factory=set)
    current_artifact_version: int | None = None
    source_start_index: int = 0
    source_end_index: int = 0
    message_order: list[str] = Field(default_factory=list)
    message_text_by_id: dict[str, str] = Field(default_factory=dict)
class ContextBudget(BaseModel):
    model_config=ConfigDict(extra='forbid')
    max_total_estimated_tokens:int=1200; max_recent_message_tokens:int=600; max_summary_tokens:int=450; max_tool_observation_tokens:int=150; min_recent_messages:int=2; max_recent_messages:int=10; compression_trigger_tokens:int=900; compression_trigger_messages:int=12
