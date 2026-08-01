from backend.agents.runtime import AgentDefinition
from backend.domain.agent_dialogue import AgentSessionStatus

from .instructions import INSTRUCTIONS
from .outputs import DesignConversationOutput, ProviderDesignConversationOutput, adapt_provider_output


DESIGN_TOOL_NAMES = frozenset({
    "inspect_design_state", "search_cultural_knowledge", "load_design_skill", "validate_design_constraints",
})

DESIGN_CONVERSATION_DEFINITION = AgentDefinition(
    name="design_conversation",
    instructions=INSTRUCTIONS,
    allowed_tools=DESIGN_TOOL_NAMES,
    output_model=DesignConversationOutput,
    max_model_requests=7,
    max_total_tool_calls=4,
    max_calls_per_tool=2,
    max_calls_by_tool={"inspect_design_state": 1, "search_cultural_knowledge": 1,
                       "load_design_skill": 1, "validate_design_constraints": 1},
    allow_parallel_tool_calls=False,
    provider_output_model=ProviderDesignConversationOutput,
    provider_output_adapter=adapt_provider_output,
)

ALLOWED_STATUSES = frozenset(status.value for status in AgentSessionStatus)
