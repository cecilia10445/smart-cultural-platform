"""Framework-neutral RuntimeEngine protocol and result orchestration."""

from __future__ import annotations

from typing import Protocol

from .context import RuntimeContext
from .models import AgentDefinition, AgentRunResult, RuntimeInput


class RuntimeEngine(Protocol):
    async def run(self, definition: AgentDefinition, context: RuntimeContext, user_input: RuntimeInput) -> AgentRunResult:
        """Run one request without exposing any provider-specific message types."""
