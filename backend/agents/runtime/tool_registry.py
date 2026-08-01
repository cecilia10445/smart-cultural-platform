"""Small, deterministic registry for explicitly declared runtime tools."""

from __future__ import annotations

from collections.abc import Iterable

from .models import ToolRisk, ToolSpec


class ToolRegistry:
    def __init__(self) -> None:
        self._specs: dict[str, ToolSpec] = {}

    def register(self, spec: ToolSpec) -> None:
        if spec.name in self._specs:
            raise ValueError(f"Tool already registered: {spec.name}")
        self._specs[spec.name] = spec

    def register_many(self, specs: Iterable[ToolSpec]) -> None:
        for spec in specs:
            self.register(spec)

    def get(self, name: str) -> ToolSpec | None:
        return self._specs.get(name)

    def require(self, name: str) -> ToolSpec:
        spec = self.get(name)
        if spec is None:
            raise KeyError(name)
        return spec

    def list_all(self) -> tuple[ToolSpec, ...]:
        return tuple(self._specs[name] for name in sorted(self._specs))

    def list_for_agent(self, agent_name: str, session_status: str) -> tuple[ToolSpec, ...]:
        return tuple(
            spec for spec in self.list_all()
            if spec.risk is not ToolRisk.FORBIDDEN
            and agent_name in spec.allowed_agents
            and session_status in spec.allowed_statuses
        )

    def export_openai_schema(self, agent_name: str, session_status: str) -> list[dict[str, object]]:
        return [
            {
                "type": "function",
                "function": {
                    "name": spec.name,
                    "description": spec.description,
                    "parameters": spec.input_model.model_json_schema(),
                },
            }
            for spec in self.list_for_agent(agent_name, session_status)
        ]
