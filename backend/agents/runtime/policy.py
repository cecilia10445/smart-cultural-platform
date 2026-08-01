"""Authorization policy; it decides but never invokes a tool handler."""

from __future__ import annotations

from .context import RuntimeContext
from .models import AgentDefinition, ToolAuthorizationDecision, ToolCall, ToolErrorCode, ToolRisk, ToolSpec


class ToolPolicy:
    def authorize(
        self,
        definition: AgentDefinition,
        context: RuntimeContext,
        spec: ToolSpec,
        call: ToolCall,
    ) -> ToolAuthorizationDecision:
        if not context.user_id or not context.session_id or not context.agent_name:
            return ToolAuthorizationDecision(False, error_code=ToolErrorCode.TOOL_POLICY_DENIED, reason="missing runtime identity")
        if context.agent_name != definition.name:
            return ToolAuthorizationDecision(False, error_code=ToolErrorCode.TOOL_POLICY_DENIED, reason="agent identity mismatch")
        if spec.name not in definition.allowed_tools or definition.name not in spec.allowed_agents:
            return ToolAuthorizationDecision(False, error_code=ToolErrorCode.TOOL_POLICY_DENIED, reason="tool not allowed for agent")
        if context.session_status not in spec.allowed_statuses:
            return ToolAuthorizationDecision(False, error_code=ToolErrorCode.TOOL_POLICY_DENIED, reason="tool not allowed for session status")
        if spec.risk is ToolRisk.FORBIDDEN:
            return ToolAuthorizationDecision(False, error_code=ToolErrorCode.TOOL_FORBIDDEN, reason="tool is forbidden")
        if spec.risk is ToolRisk.HIGH_RISK:
            return ToolAuthorizationDecision(False, approval_required=True, error_code=ToolErrorCode.TOOL_APPROVAL_REQUIRED, reason="high-risk tool requires approval")
        return ToolAuthorizationDecision(True, reason="tool allowed")
