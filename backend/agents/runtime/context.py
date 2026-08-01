"""Request-scoped dependencies for a runtime invocation."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping


@dataclass(frozen=True, slots=True)
class RuntimeContext:
    user_id: str
    session_id: str
    agent_name: str
    session_status: str
    services: Mapping[str, Any] = field(default_factory=dict, repr=False)
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for name in ("user_id", "session_id", "agent_name"):
            if not getattr(self, name).strip():
                raise ValueError(f"{name} must not be empty")
