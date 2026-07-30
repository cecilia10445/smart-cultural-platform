from backend.agents.runtime import AgentDefinition
from backend.domain.agent_dialogue import AgentSessionStatus

from .instructions import INSTRUCTIONS
from .outputs import DesignConversationOutput


DESIGN_TOOL_NAMES = frozenset({
    "inspect_design_state", "search_cultural_knowledge", "load_design_skill", "validate_design_constraints",
})

DESIGN_CONVERSATION_DEFINITION = AgentDefinition(
    name="design_conversation",
    instructions=INSTRUCTIONS,
    allowed_tools=DESIGN_TOOL_NAMES,
    output_model=DesignConversationOutput,
    max_model_requests=5,
    max_total_tool_calls=4,
    max_calls_per_tool=2,
    allow_parallel_tool_calls=False,
)

ALLOWED_STATUSES = frozenset(status.value for status in AgentSessionStatus)
